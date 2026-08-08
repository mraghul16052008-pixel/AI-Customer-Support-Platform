from dataclasses import dataclass, replace
import logging
from math import isfinite
from typing import Mapping

from app.services.intent_router import IntentRouter, RoutingOutcome
from app.services.support_agents import AgentOutcome, SpecializedSupportAgent, create_agent_registry
from app.services.support_tools import ContextSupportTools, TrustedSupportTools
from app.services.support_types import (
    AgentAction,
    EvidenceAnalysis,
    RecommendedResolution,
    RoutingDecision,
    SupportContext,
    SupportIntent,
    SupportProvider,
    SupportResult,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ProviderObservation:
    selected_provider: str
    request_attempted: bool
    provider_succeeded: bool
    fallback_used: bool
    error_type: str | None = None
    error_code: str | int | None = None
    error_status: str | None = None
    router_used: str = "IntentRouter"
    router_provider_succeeded: bool = False
    router_fallback_used: bool = False
    selected_intent: SupportIntent | None = None
    selected_agent: str | None = None
    specialist_provider_succeeded: bool = False
    specialist_fallback_used: bool = False
    confidence: float | None = None
    should_escalate: bool | None = None
    agent_action: AgentAction | None = None
    recommended_resolution: RecommendedResolution | None = None
    missing_information: tuple[str, ...] = ()
    evidence_needed: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()


class DeterministicSupportProvider:
    def __init__(self) -> None:
        self.router = IntentRouter()
        self.agents = create_agent_registry()

    def respond(self, context: SupportContext) -> SupportResult:
        routing = self.router.route(context).decision
        result = self.agents[routing.intent].handle(context).result
        return SupportResult(
            reply=result.reply,
            intent=routing.intent,
            confidence=min(float(routing.confidence), float(result.confidence)),
            should_escalate=result.should_escalate,
            escalation_reason=result.escalation_reason,
            action=result.action,
            missing_information=result.missing_information,
            evidence_needed=result.evidence_needed,
            findings=result.findings,
            recommended_resolution=result.recommended_resolution,
        )


class SupportAIService:
    def __init__(
        self,
        provider: SupportProvider | object | None = None,
        *,
        router: IntentRouter | None = None,
        agents: Mapping[SupportIntent, SpecializedSupportAgent] | None = None,
        tools: TrustedSupportTools | None = None,
    ) -> None:
        self.provider = provider
        routing_provider = provider if provider is not None and hasattr(provider, "route") else None
        self.router = router or IntentRouter(routing_provider)  # type: ignore[arg-type]
        self.agents = dict(agents or create_agent_registry(provider))
        self.tools = tools or ContextSupportTools()
        missing_agents = set(SupportIntent) - set(self.agents)
        if missing_agents:
            raise ValueError("Agent registry is missing: " + ", ".join(sorted(i.value for i in missing_agents)))
        self.fallback = DeterministicSupportProvider()
        provider_name = type(provider).__name__ if provider is not None else type(self.fallback).__name__
        self.last_observation = ProviderObservation(
            selected_provider=provider_name,
            request_attempted=False,
            provider_succeeded=False,
            fallback_used=provider is None,
        )

    def respond(self, context: SupportContext) -> SupportResult:
        routing = self.router.route(context)
        routing_decision = routing.decision
        context = replace(
            context,
            trusted_evidence=self.tools.evidence_for(routing_decision.intent, context),
        )
        agent = self.agents[routing_decision.intent]
        logger.info(
            "AI router used: router=%s selected_intent=%s confidence=%.2f agent=%s",
            type(self.router).__name__, routing_decision.intent.value,
            routing_decision.confidence, agent.name,
        )
        execution = agent.handle(context)
        if execution.result.intent != routing_decision.intent:
            execution = AgentOutcome(
                result=self.fallback.respond(context),
                provider_attempted=execution.provider_attempted,
                provider_succeeded=False,
                fallback_used=True,
                error_type="ValueError",
            )

        combined = SupportResult(
            reply=execution.result.reply,
            intent=routing_decision.intent,
            confidence=min(float(routing_decision.confidence), float(execution.result.confidence)),
            should_escalate=execution.result.should_escalate,
            escalation_reason=execution.result.escalation_reason,
            action=execution.result.action,
            missing_information=execution.result.missing_information,
            evidence_needed=execution.result.evidence_needed,
            findings=execution.result.findings,
            recommended_resolution=execution.result.recommended_resolution,
        )
        try:
            result = self._apply_backend_safety(combined, context)
        except Exception:
            fallback = self.fallback.respond(context)
            result = self._apply_backend_safety(fallback, context)
            execution = AgentOutcome(
                result=fallback,
                provider_attempted=execution.provider_attempted,
                provider_succeeded=False,
                fallback_used=True,
                error_type="ValueError",
            )

        fallback_used = routing.fallback_used or execution.fallback_used
        request_attempted = routing.provider_attempted or execution.provider_attempted
        provider_succeeded = routing.provider_succeeded and (
            not execution.provider_attempted or execution.provider_succeeded
        )
        agent_decision = execution.decision
        self.last_observation = ProviderObservation(
            selected_provider=type(self.provider).__name__ if self.provider is not None else type(self.fallback).__name__,
            request_attempted=request_attempted,
            provider_succeeded=provider_succeeded,
            fallback_used=fallback_used,
            error_type=execution.error_type or routing.error_type,
            error_code=execution.error_code or routing.error_code,
            error_status=execution.error_status or routing.error_status,
            router_used=type(self.router).__name__,
            router_provider_succeeded=routing.provider_succeeded,
            router_fallback_used=routing.fallback_used,
            selected_intent=routing_decision.intent,
            selected_agent=agent.name,
            specialist_provider_succeeded=execution.provider_succeeded,
            specialist_fallback_used=execution.fallback_used,
            confidence=result.confidence,
            should_escalate=result.should_escalate,
            agent_action=agent_decision.action if agent_decision else None,
            recommended_resolution=agent_decision.recommended_resolution if agent_decision else None,
            missing_information=agent_decision.missing_information if agent_decision else (),
            evidence_needed=agent_decision.evidence_needed if agent_decision else (),
            findings=agent_decision.findings if agent_decision else (),
        )
        logger.info(
            "AI agent completed: intent=%s agent=%s router_provider=%s specialist_provider=%s fallback=%s confidence=%.2f escalate=%s",
            routing_decision.intent.value, agent.name, routing.provider_succeeded,
            execution.provider_succeeded, fallback_used, result.confidence,
            result.should_escalate,
        )
        return result

    @staticmethod
    def _apply_backend_safety(result: SupportResult, context: SupportContext) -> SupportResult:
        if not isinstance(result.intent, SupportIntent):
            raise ValueError("Provider returned an unsupported intent.")
        if not isinstance(result.reply, str) or not result.reply.strip():
            raise ValueError("Provider returned an empty reply.")
        if not isinstance(result.confidence, (int, float)) or not isfinite(result.confidence):
            raise ValueError("Provider confidence must be a finite number.")
        if not 0.0 <= result.confidence <= 1.0:
            raise ValueError("Provider confidence must be between 0 and 1.")

        text = context.message.casefold()
        refund = result.intent == SupportIntent.REFUND or any(t in text for t in ("refund", "money back", "return"))
        payment = result.intent == SupportIntent.PAYMENT_ISSUE or any(t in text for t in ("charged", "payment", "card", "billing"))
        cancellation = result.intent == SupportIntent.CANCELLATION or "cancel" in text
        delivery_security = any(t in text for t in ("lost", "damaged"))
        account_security = any(t in text for t in ("hacked", "unauthorized", "stolen", "suspicious"))
        resolved_followup = (
            context.escalation_status == "RESOLVED"
            and bool(context.human_response)
            and any(
                term in text
                for term in ("decision", "update", "resolved", "approved", "human agent", "support agent")
            )
        )
        sensitive_reason = None
        if refund:
            sensitive_reason = "Refund requests require human review."
        elif payment:
            sensitive_reason = "Payment issues require secure human review."
        elif cancellation:
            sensitive_reason = "Cancellation requests require human review."
        elif delivery_security:
            sensitive_reason = "A lost or damaged delivery requires human review."
        elif account_security:
            sensitive_reason = "A possible account security issue requires human review."

        should_escalate = False if resolved_followup else (
            result.should_escalate or result.confidence < 0.70 or sensitive_reason is not None
        )
        escalation_reason = result.escalation_reason
        if resolved_followup:
            escalation_reason = None
        elif sensitive_reason is not None:
            escalation_reason = sensitive_reason
        elif should_escalate and not escalation_reason:
            escalation_reason = (
                f"Low-confidence {result.intent.value} request ({result.confidence:.2f})."
                if result.confidence < 0.70 else "Support agent recommended human review."
            )

        reply = result.reply.strip()
        if SupportAIService._contains_unsupported_claim(reply, result.intent, context):
            reply = create_agent_registry()[result.intent].handle(context).result.reply
        return SupportResult(
            reply=reply,
            intent=result.intent,
            confidence=float(result.confidence),
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
            action=result.action,
            missing_information=result.missing_information,
            evidence_needed=result.evidence_needed,
            findings=result.findings,
            recommended_resolution=result.recommended_resolution,
        )

    @staticmethod
    def _contains_unsupported_claim(reply: str, intent: SupportIntent, context: SupportContext) -> bool:
        text = reply.casefold()
        if intent == SupportIntent.ORDER_STATUS:
            facts = ("arrive tomorrow", "arrives tomorrow", "courier is", "tracking number", "out for delivery", "has shipped", "was delivered")
            if any(term in text for term in facts):
                return not context.order_status or context.order_status.casefold() not in text
        if intent == SupportIntent.DELIVERY_ISSUE and any(
            term in text for term in ("arrive tomorrow", "arrives tomorrow", "courier is", "tracking number")
        ):
            return True
        if intent == SupportIntent.REFUND and any(t in text for t in ("refund approved", "refund issued", "refund sent")):
            return True
        if intent == SupportIntent.CANCELLATION and any(t in text for t in ("i cancelled", "i canceled", "is now cancelled", "is now canceled")):
            return True
        secrets = ("card number", "cvv", "otp", "password", "recovery code")
        requests = ("send your", "share your", "provide your", "tell me your")
        return any(t in text for t in requests) and any(t in text for t in secrets)

    def analyze_evidence(self, context: SupportContext, image_bytes: bytes, media_type: str) -> EvidenceAnalysis:
        if self.provider is not None and hasattr(self.provider, "analyze_evidence"):
            try:
                analysis = self.provider.analyze_evidence(context, image_bytes, media_type)  # type: ignore[union-attr]
                if not 0.0 <= analysis.confidence <= 1.0:
                    raise ValueError("Evidence confidence must be between 0 and 1.")
                if analysis.recommended_resolution not in {
                    RecommendedResolution.INVESTIGATE,
                    RecommendedResolution.REFUND,
                    RecommendedResolution.REPLACE,
                }:
                    raise ValueError("Evidence recommendation is unsupported.")
                return analysis
            except Exception as exc:
                logger.warning(
                    "Evidence provider failed; safe human-review fallback used: "
                    "type=%s code=%s status=%s",
                    type(exc).__name__, getattr(exc, "code", None),
                    getattr(exc, "status", None),
                )
        return EvidenceAnalysis(
            findings=("Customer-supplied image received; automated analysis is unavailable.",),
            limitations=("A human must review the original customer-supplied image.",),
            confidence=0.0,
            recommended_resolution=RecommendedResolution.INVESTIGATE,
        )


__all__ = [
    "DeterministicSupportProvider", "IntentRouter", "ProviderObservation",
    "RoutingDecision", "RoutingOutcome", "SupportAIService", "SupportContext",
    "SupportIntent", "SupportProvider", "SupportResult",
]
