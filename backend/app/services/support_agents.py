from dataclasses import dataclass
from typing import Mapping

from app.services.support_types import (
    AgentAction,
    AgentDecision,
    RecommendedResolution,
    SpecialistProvider,
    SupportContext,
    SupportIntent,
    SupportProvider,
    SupportResult,
)


@dataclass(frozen=True)
class AgentOutcome:
    result: SupportResult
    provider_attempted: bool
    provider_succeeded: bool
    fallback_used: bool
    decision: AgentDecision | None = None
    error_type: str | None = None
    error_code: str | int | None = None
    error_status: str | None = None


def _history_contains(context: SupportContext, *terms: str) -> bool:
    return any(
        term in turn.content.casefold()
        for turn in context.history
        for term in terms
    )


def _customer_turn_count(context: SupportContext) -> int:
    return sum(turn.sender_type == "CUSTOMER" for turn in context.history)


def _customer_evidence(context: SupportContext) -> tuple[str, ...]:
    return tuple(
        turn.content
        for turn in context.history
        if turn.sender_type == "CUSTOMER_EVIDENCE"
    )


class SpecializedSupportAgent:
    intent: SupportIntent
    instructions: str

    def __init__(self, provider: object | None = None) -> None:
        self.provider = provider

    @property
    def name(self) -> str:
        return type(self).__name__

    def handle(self, context: SupportContext) -> AgentOutcome:
        if self.provider is None:
            decision = self._resolved_human_decision(context) or self._deterministic_decision(context)
            return AgentOutcome(
                result=self._to_result(decision),
                decision=decision,
                provider_attempted=False,
                provider_succeeded=False,
                fallback_used=True,
            )
        try:
            decision = self._call_provider(context)
            self._validate_decision(decision)
            return AgentOutcome(
                result=self._to_result(decision),
                decision=decision,
                provider_attempted=True,
                provider_succeeded=True,
                fallback_used=False,
            )
        except Exception as exc:
            decision = self._resolved_human_decision(context) or self._deterministic_decision(context)
            code = getattr(exc, "code", None)
            status = getattr(exc, "status", None)
            return AgentOutcome(
                result=self._to_result(decision),
                decision=decision,
                provider_attempted=True,
                provider_succeeded=False,
                fallback_used=True,
                error_type=type(exc).__name__,
                error_code=code if isinstance(code, (str, int)) else None,
                error_status=str(status) if status is not None else None,
            )

    def _call_provider(self, context: SupportContext) -> AgentDecision:
        if hasattr(self.provider, "investigate"):
            return self.provider.investigate(  # type: ignore[union-attr]
                self.intent, context, self.instructions
            )
        if hasattr(self.provider, "respond_for_intent"):
            result = self.provider.respond_for_intent(  # type: ignore[union-attr]
                self.intent, context, self.instructions
            )
        elif hasattr(self.provider, "respond"):
            result = self.provider.respond(context)  # type: ignore[union-attr]
        else:
            raise TypeError("Specialist provider is incompatible.")
        if result.intent != self.intent:
            raise ValueError("Specialist returned an intent outside its role.")
        return AgentDecision(
            reply=result.reply,
            confidence=result.confidence,
            action=(
                AgentAction.ESCALATE
                if result.should_escalate
                else AgentAction.ANSWER
            ),
            escalation_reason=result.escalation_reason,
        )

    def _to_result(self, decision: AgentDecision) -> SupportResult:
        return SupportResult(
            reply=decision.reply,
            intent=self.intent,
            confidence=decision.confidence,
            should_escalate=decision.action
            in (AgentAction.ESCALATE, AgentAction.REQUEST_HUMAN_DECISION),
            escalation_reason=decision.escalation_reason,
            action=decision.action,
            missing_information=decision.missing_information,
            evidence_needed=decision.evidence_needed,
            findings=decision.findings,
            recommended_resolution=decision.recommended_resolution,
        )

    @staticmethod
    def _validate_decision(decision: AgentDecision) -> None:
        if not decision.reply.strip():
            raise ValueError("Specialist returned an empty reply.")
        if not 0.0 <= decision.confidence <= 1.0:
            raise ValueError("Specialist confidence must be between 0 and 1.")
        if not isinstance(decision.action, AgentAction):
            raise ValueError("Specialist returned an unsupported action.")
        if not isinstance(decision.recommended_resolution, RecommendedResolution):
            raise ValueError("Specialist returned an unsupported recommendation.")

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        raise NotImplementedError

    @staticmethod
    def _resolved_human_decision(context: SupportContext) -> AgentDecision | None:
        asks_for_update = any(
            term in context.message.casefold()
            for term in ("decision", "update", "resolved", "approved", "human agent", "support agent")
        )
        if context.escalation_status == "RESOLVED" and context.human_response and asks_for_update:
            return AgentDecision(
                reply=(
                    "The human support decision recorded for this case is: "
                    f"{context.human_response} If you have a new or unresolved issue, "
                    "tell me what remains wrong and I can investigate it."
                ),
                confidence=0.99,
                action=AgentAction.ANSWER,
                findings=("A resolved human decision is available in the trusted case record.",),
            )
        return None


class OrderStatusAgent(SpecializedSupportAgent):
    intent = SupportIntent.ORDER_STATUS
    instructions = (
        "Investigate the customer's order question conversationally. Use only trusted "
        "order/tool data. Never invent a date, courier location, tracking number, "
        "shipping event, or status. Consider recent history and ask a targeted "
        "follow-up only when it helps identify a delivery problem."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        if context.order_status:
            product = context.product_name or "selected"
            order_ref = f" #{context.external_order_id}" if context.external_order_id else ""
            reply = (
                f"I checked order{order_ref} for your {product}. The current status is "
                f"{context.order_status}, the latest status available in ShopX. "
                "I don't have a confirmed delivery "
                "date or courier location in the current ShopX data. If you're asking "
                "because something seems delayed, tell me what happened and I'll "
                "investigate further."
            )
            return AgentDecision(reply, 0.93, AgentAction.ANSWER)
        return AgentDecision(
            "I don't have an order attached to this conversation, so I can't verify "
            "its current status. Please open support from a saved order and I'll "
            "inspect the available ShopX record.",
            0.91,
            AgentAction.ASK_CUSTOMER,
            missing_information=("attached order",),
        )


class DeliverySupportAgent(SpecializedSupportAgent):
    intent = SupportIntent.DELIVERY_ISSUE
    instructions = (
        "Investigate late, missing, lost, or damaged deliveries. Use recent history. "
        "For damage, request useful customer evidence if it has not already been "
        "requested: item, outer packaging, and shipping-label photos. Clearly separate "
        "customer evidence from trusted packing evidence. Never infer fault, invent "
        "courier facts, or claim packing evidence exists when tools say unavailable. "
        "Any refund/replacement recommendation requires a human decision."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        combined = " ".join(
            [context.message, *(turn.content for turn in context.history)]
        ).casefold()
        evidence_issue = any(
            term in combined
            for term in ("damaged", "wrong item", "wrong product", "incorrect item", "replace", "replacement")
        )
        lost_or_missing = any(
            term in combined for term in ("lost", "not delivered", "not arrived", "missing")
        )
        evidence = _customer_evidence(context)
        asked_before = _history_contains(
            context, "damaged item photo", "outer packaging photo", "shipping label photo"
        )
        packing = next(
            (
                item
                for item in context.trusted_evidence
                if item.source == "packing_evidence"
            ),
            None,
        )

        if evidence_issue and not evidence and not asked_before:
            detail_prefix = (
                "Thanks, I've added that detail to the investigation. "
                if context.history
                else ""
            )
            return AgentDecision(
                reply=(
                    detail_prefix
                    + "I'm sorry the delivered item is damaged or does not match the order. "
                    "To document what happened, could you upload a clear photo of the "
                    "item first? If "
                    "available, an outer-packaging photo and shipping-label photo also "
                    "help a human agent review the case. I need these as customer "
                    "evidence; ShopX currently has no trusted packing photos to compare."
                ),
                confidence=0.92,
                action=AgentAction.REQUEST_EVIDENCE,
                missing_information=("condition of item and package",),
                evidence_needed=(
                    "affected item photo",
                    "outer packaging photo",
                    "shipping label photo",
                ),
                recommended_resolution=RecommendedResolution.INVESTIGATE,
                escalation_reason="Damaged or incorrect delivery requires human review and evidence assessment.",
            )

        if evidence_issue and not evidence:
            return AgentDecision(
                reply=(
                    "Thanks, I've added that detail to the investigation. I haven't received image "
                    "evidence, and I won't ask you for the same photos again. I also "
                    "cannot compare the shipment with trusted packing evidence because "
                    "that source is unavailable. I'll send the available conversation "
                    "and order record to a human agent for the next decision."
                ),
                confidence=0.83,
                action=AgentAction.REQUEST_HUMAN_DECISION,
                findings=("Customer reports a damaged or lost delivery.",),
                recommended_resolution=RecommendedResolution.INVESTIGATE,
                escalation_reason="Delivery issue needs human review; requested evidence is unavailable.",
            )

        if evidence_issue and evidence:
            visible_damage = any(
                "visible damage" in item.casefold() or "damage visible" in item.casefold()
                for item in evidence
            )
            recommendation = (
                RecommendedResolution.REPLACE
                if visible_damage
                else RecommendedResolution.INVESTIGATE
            )
            if packing and packing.available:
                packing_text = (
                    f"The {'DEMO ' if packing.is_demo else ''}trusted packing source "
                    f"reports: {packing.summary}"
                )
            else:
                packing_text = (
                    "No trusted ShopX packing evidence is available for comparison."
                )
            return AgentDecision(
                reply=(
                    "I've reviewed the customer-supplied evidence summary. The "
                    f"available evidence suggests the reported damage needs review. "
                    f"{packing_text} My recommendation is {recommendation.value.lower()}, "
                    "but a human agent must make the final decision."
                ),
                confidence=0.86 if visible_damage else 0.76,
                action=AgentAction.REQUEST_HUMAN_DECISION,
                findings=("Customer-supplied image evidence is present.",),
                recommended_resolution=recommendation,
                escalation_reason=(
                    f"Customer evidence reviewed; AI recommendation: {recommendation.value}. "
                    "Human approval required."
                ),
            )

        if lost_or_missing:
            already_answered = _history_contains(
                context, "expected delivery", "carrier notice", "delivery notification"
            )
            if not already_answered:
                status = context.order_status or "unavailable"
                return AgentDecision(
                    reply=(
                        f"I can confirm the trusted ShopX order status is {status}, but "
                        "no trusted tracking events or courier location are available. "
                        "When was it expected, and did you receive any carrier delivery notice?"
                    ),
                    confidence=0.85,
                    action=AgentAction.ASK_CUSTOMER,
                    missing_information=("expected delivery date", "carrier notice"),
                    recommended_resolution=RecommendedResolution.INVESTIGATE,
                )
            return AgentDecision(
                reply=(
                    "I've recorded the delivery details you provided. ShopX has no "
                    "trusted tracking events available to verify the parcel location, "
                    "so a human agent needs to investigate the carrier outcome."
                ),
                confidence=0.78,
                action=AgentAction.REQUEST_HUMAN_DECISION,
                findings=("Customer reports the order was not received.",),
                recommended_resolution=RecommendedResolution.INVESTIGATE,
                escalation_reason="Missing delivery requires human investigation; trusted tracking is unavailable.",
            )

        if context.order_status:
            return AgentDecision(
                f"I checked the trusted order record; the verified ShopX status is "
                f"{context.order_status}. I don't have a confirmed delivery date or "
                "courier location. What specifically happened with the delivery?",
                0.86,
                AgentAction.ASK_CUSTOMER,
                missing_information=("specific delivery problem",),
            )
        return AgentDecision(
            "I'm sorry about the delivery problem. No order is attached, so I can't "
            "verify its status. Which saved order is affected?",
            0.66,
            AgentAction.ASK_CUSTOMER,
            missing_information=("affected order",),
        )


class RefundAgent(SpecializedSupportAgent):
    intent = SupportIntent.REFUND
    instructions = (
        "Investigate the reason, order, return state, evidence, and available policy "
        "data. Never claim eligibility, approval, amount, timing, or payment. Ask one "
        "targeted follow-up if needed. A human must approve any refund."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        if _customer_turn_count(context) == 0:
            return AgentDecision(
                "I can investigate the refund request, but I need to understand what "
                "happened first. Was the item damaged, incorrect, not received, or are "
                "you returning it for another reason? I haven't approved or issued a "
                "refund; any decision requires human review.",
                0.82,
                AgentAction.ASK_CUSTOMER,
                missing_information=("refund reason", "return state"),
                recommended_resolution=RecommendedResolution.INVESTIGATE,
                escalation_reason="Refund request requires investigation and human approval.",
            )
        return AgentDecision(
            "Thanks—that reason is now part of the investigation. I can confirm only "
            "the current ShopX order record; no return-state or refund-policy tool is "
            "available here. My recommendation is human review before any refund decision.",
            0.78,
            AgentAction.REQUEST_HUMAN_DECISION,
            findings=("Customer supplied a refund reason in the conversation.",),
            recommended_resolution=RecommendedResolution.REFUND,
            escalation_reason="AI recommends refund review; human approval is mandatory.",
        )


class CancellationAgent(SpecializedSupportAgent):
    intent = SupportIntent.CANCELLATION
    instructions = (
        "Inspect the trusted order status. Never claim cancellation occurred. Explain "
        "that the current backend has no cancellation action and request human approval."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        status = context.order_status or "unavailable"
        return AgentDecision(
            f"I checked the available order record; its current status is {status}. "
            "This support service has no cancellation action, so nothing has been "
            "cancelled. I recommend a human agent review whether cancellation is still possible.",
            0.91,
            AgentAction.REQUEST_HUMAN_DECISION,
            findings=(f"Trusted order status: {status}.",),
            recommended_resolution=RecommendedResolution.CANCEL,
            escalation_reason="Cancellation requires a human business decision.",
        )


class PaymentSupportAgent(SpecializedSupportAgent):
    intent = SupportIntent.PAYMENT_ISSUE
    instructions = (
        "Investigate only safe payment metadata from trusted tools. Never ask for a "
        "card number, CVV, OTP, password, recovery code, or bank credential. Duplicate "
        "charges and disputes require a human payment decision."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        metadata = next(
            (
                item
                for item in context.trusted_evidence
                if item.source == "payment_metadata"
            ),
            None,
        )
        availability = (
            metadata.summary
            if metadata and metadata.available
            else "No safe payment metadata is available in the current backend."
        )
        return AgentDecision(
            "I'm sorry about the payment issue. "
            f"{availability} Please share only the charge date and amount shown on "
            "your statement—never a card number, CVV, OTP, password, or bank credential. "
            "A human payment specialist must make the final decision.",
            0.88,
            AgentAction.REQUEST_HUMAN_DECISION,
            missing_information=("charge date", "charge amount"),
            recommended_resolution=RecommendedResolution.PAYMENT_REVIEW,
            escalation_reason="Payment issue requires secure human review.",
        )


class AccountSupportAgent(SpecializedSupportAgent):
    intent = SupportIntent.ACCOUNT_ISSUE
    instructions = (
        "Ask useful non-sensitive questions and remember prior answers. Never ask for "
        "passwords, OTPs, verification or recovery codes. Suspected compromise requires "
        "immediate human security review."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        combined = " ".join(
            [context.message, *(turn.content for turn in context.history)]
        ).casefold()
        compromised = any(
            term in combined
            for term in ("hacked", "unauthorized", "stolen", "suspicious")
        )
        if compromised:
            return AgentDecision(
                "Possible unauthorized account activity needs immediate human review. "
                "Please don't share your password, OTP, verification code, or recovery "
                "code. A support agent will review the security issue.",
                0.94,
                AgentAction.REQUEST_HUMAN_DECISION,
                recommended_resolution=RecommendedResolution.SECURITY_REVIEW,
                escalation_reason="Possible account compromise requires human security review.",
            )
        return AgentDecision(
            "What error do you see when signing in, and have you already tried the "
            "secure ShopX password-reset flow? Please don't include any password, OTP, "
            "verification code, or recovery code.",
            0.82,
            AgentAction.ASK_CUSTOMER,
            missing_information=("sign-in error", "password reset attempted"),
        )


class GeneralSupportAgent(SpecializedSupportAgent):
    intent = SupportIntent.GENERAL_QUERY
    instructions = (
        "Have a concise clarification dialogue. Use recent history and ask one useful "
        "question at a time. Do not invent order, policy, account, payment, or delivery facts."
    )

    def _deterministic_decision(self, context: SupportContext) -> AgentDecision:
        return AgentDecision(
            "I want to understand the issue before giving you the wrong answer. Is "
            "this about an order, delivery, return or refund, payment, cancellation, "
            "or your ShopX account?",
            0.55,
            AgentAction.ASK_CUSTOMER,
            missing_information=("support category",),
            recommended_resolution=RecommendedResolution.INVESTIGATE,
            escalation_reason="Low-confidence general request needs clarification or human review.",
        )


def create_agent_registry(
    provider: SpecialistProvider | SupportProvider | object | None = None,
) -> Mapping[SupportIntent, SpecializedSupportAgent]:
    agents = (
        OrderStatusAgent(provider),
        DeliverySupportAgent(provider),
        RefundAgent(provider),
        CancellationAgent(provider),
        PaymentSupportAgent(provider),
        AccountSupportAgent(provider),
        GeneralSupportAgent(provider),
    )
    return {agent.intent: agent for agent in agents}
