from dataclasses import dataclass
from enum import StrEnum
import logging
from math import isfinite
from typing import Protocol


logger = logging.getLogger(__name__)


class SupportIntent(StrEnum):
    ORDER_STATUS = "order_status"
    DELIVERY_ISSUE = "delivery_issue"
    REFUND = "refund"
    CANCELLATION = "cancellation"
    PAYMENT_ISSUE = "payment_issue"
    ACCOUNT_ISSUE = "account_issue"
    GENERAL_QUERY = "general_query"


@dataclass(frozen=True)
class SupportContext:
    message: str
    customer_name: str | None = None
    order_status: str | None = None
    external_order_id: str | None = None
    product_name: str | None = None


@dataclass(frozen=True)
class SupportResult:
    reply: str
    intent: SupportIntent
    confidence: float
    should_escalate: bool
    escalation_reason: str | None = None


@dataclass(frozen=True)
class ProviderObservation:
    selected_provider: str
    request_attempted: bool
    provider_succeeded: bool
    fallback_used: bool
    error_type: str | None = None
    error_code: str | int | None = None
    error_status: str | None = None


class SupportProvider(Protocol):
    def respond(self, context: SupportContext) -> SupportResult: ...


class DeterministicSupportProvider:
    def respond(self, context: SupportContext) -> SupportResult:
        text = context.message.casefold()

        if any(term in text for term in ("refund", "money back", "return my")):
            return self._result(
                reply=(
                    "I’ll send your refund request to a support specialist for review."
                ),
                intent=SupportIntent.REFUND,
                confidence=0.94,
                force_escalation_reason="Refund requests require human review.",
            )

        if any(term in text for term in ("charged", "payment", "card", "billing")):
            return self._result(
                reply=(
                    "I’m escalating this payment issue so a support specialist can "
                    "review it safely."
                ),
                intent=SupportIntent.PAYMENT_ISSUE,
                confidence=0.92,
                force_escalation_reason="Payment issues require secure human review.",
            )

        if any(term in text for term in ("cancel", "cancellation")):
            return self._result(
                reply=(
                    "I’ll send your cancellation request to a support specialist "
                    "before any action is taken."
                ),
                intent=SupportIntent.CANCELLATION,
                confidence=0.93,
                force_escalation_reason="Cancellation requests require human review.",
            )

        if any(
            term in text
            for term in (
                "late",
                "delayed",
                "not arrived",
                "not delivered",
                "damaged",
                "lost",
            )
        ):
            sensitive = any(term in text for term in ("lost", "damaged"))
            return self._result(
                reply=(
                    "I’m sorry about the delivery problem. I’ve recorded the issue "
                    "and will help with the next step."
                ),
                intent=SupportIntent.DELIVERY_ISSUE,
                confidence=0.90,
                force_escalation_reason=(
                    "A lost or damaged delivery requires human review."
                    if sensitive
                    else None
                ),
            )

        if any(
            term in text
            for term in ("where is my order", "order status", "track", "tracking")
        ):
            if context.order_status:
                reply = f"Your order is currently {context.order_status}."
            else:
                reply = "I can help check the order status once an order is selected."
            return self._result(
                reply=reply,
                intent=SupportIntent.ORDER_STATUS,
                confidence=0.91,
            )

        if any(term in text for term in ("account", "login", "password", "sign in")):
            sensitive = any(
                term in text for term in ("hacked", "unauthorized", "stolen")
            )
            return self._result(
                reply="I can help with your account issue.",
                intent=SupportIntent.ACCOUNT_ISSUE,
                confidence=0.87,
                force_escalation_reason=(
                    "A possible account security issue requires human review."
                    if sensitive
                    else None
                ),
            )

        return self._result(
            reply=(
                "I’m not fully certain what you need, so I’m connecting this "
                "conversation with a support specialist."
            ),
            intent=SupportIntent.GENERAL_QUERY,
            confidence=0.55,
        )

    @staticmethod
    def _result(
        *,
        reply: str,
        intent: SupportIntent,
        confidence: float,
        force_escalation_reason: str | None = None,
    ) -> SupportResult:
        confidence = max(0.0, min(1.0, confidence))
        should_escalate = confidence < 0.70 or force_escalation_reason is not None
        reason = force_escalation_reason
        if should_escalate and reason is None:
            reason = f"Low-confidence {intent.value} request ({confidence:.2f})."
        return SupportResult(
            reply=reply,
            intent=intent,
            confidence=confidence,
            should_escalate=should_escalate,
            escalation_reason=reason,
        )


class SupportAIService:
    def __init__(self, provider: SupportProvider | None = None) -> None:
        self.provider = provider
        self.fallback = DeterministicSupportProvider()
        self.last_observation = ProviderObservation(
            selected_provider=(
                type(provider).__name__
                if provider is not None
                else type(self.fallback).__name__
            ),
            request_attempted=False,
            provider_succeeded=False,
            fallback_used=provider is None,
        )

    def respond(self, context: SupportContext) -> SupportResult:
        if self.provider is not None:
            provider_name = type(self.provider).__name__
            logger.info("AI provider selected: %s", provider_name)
            self.last_observation = ProviderObservation(
                selected_provider=provider_name,
                request_attempted=True,
                provider_succeeded=False,
                fallback_used=False,
            )
            try:
                result = self._apply_backend_safety(
                    self.provider.respond(context), context
                )
                self.last_observation = ProviderObservation(
                    selected_provider=provider_name,
                    request_attempted=True,
                    provider_succeeded=True,
                    fallback_used=False,
                )
                logger.info("AI provider request succeeded: %s", provider_name)
                return result
            except Exception as exc:
                error_code = getattr(exc, "code", None)
                error_status = getattr(exc, "status", None)
                self.last_observation = ProviderObservation(
                    selected_provider=provider_name,
                    request_attempted=True,
                    provider_succeeded=False,
                    fallback_used=True,
                    error_type=type(exc).__name__,
                    error_code=(
                        error_code
                        if isinstance(error_code, (str, int))
                        else None
                    ),
                    error_status=(
                        str(error_status) if error_status is not None else None
                    ),
                )
                logger.info(
                    "AI provider failed; deterministic fallback used: "
                    "provider=%s error_type=%s error_code=%s error_status=%s",
                    provider_name,
                    type(exc).__name__,
                    self.last_observation.error_code,
                    self.last_observation.error_status,
                )
        else:
            logger.info("AI provider selected: DeterministicSupportProvider")
            self.last_observation = ProviderObservation(
                selected_provider=type(self.fallback).__name__,
                request_attempted=False,
                provider_succeeded=False,
                fallback_used=True,
            )
        return self._apply_backend_safety(self.fallback.respond(context), context)

    @staticmethod
    def _apply_backend_safety(
        result: SupportResult, context: SupportContext
    ) -> SupportResult:
        if not isinstance(result.intent, SupportIntent):
            raise ValueError("Provider returned an unsupported intent.")
        if not result.reply.strip():
            raise ValueError("Provider returned an empty reply.")
        if not isinstance(result.confidence, (int, float)) or not isfinite(
            result.confidence
        ):
            raise ValueError("Provider confidence must be a finite number.")
        if not 0.0 <= result.confidence <= 1.0:
            raise ValueError("Provider confidence must be between 0 and 1.")

        text = context.message.casefold()
        sensitive_reason = None
        if result.intent == SupportIntent.REFUND or any(
            term in text for term in ("refund", "money back")
        ):
            sensitive_reason = "Refund requests require human review."
        elif result.intent == SupportIntent.PAYMENT_ISSUE or any(
            term in text for term in ("charged", "payment", "card", "billing")
        ):
            sensitive_reason = "Payment issues require secure human review."
        elif result.intent == SupportIntent.CANCELLATION or any(
            term in text for term in ("cancel", "cancellation")
        ):
            sensitive_reason = "Cancellation requests require human review."
        elif any(term in text for term in ("lost", "damaged")):
            sensitive_reason = "A lost or damaged delivery requires human review."
        elif any(
            term in text
            for term in ("hacked", "unauthorized", "stolen", "suspicious")
        ):
            sensitive_reason = "A possible account security issue requires human review."

        should_escalate = (
            result.should_escalate
            or result.confidence < 0.70
            or sensitive_reason is not None
        )
        escalation_reason = result.escalation_reason
        if should_escalate and not escalation_reason:
            if sensitive_reason:
                escalation_reason = sensitive_reason
            elif result.confidence < 0.70:
                escalation_reason = (
                    f"Low-confidence {result.intent.value} request "
                    f"({result.confidence:.2f})."
                )
            else:
                escalation_reason = "Support provider recommended human review."
        reply = result.reply.strip()
        if result.intent == SupportIntent.ORDER_STATUS:
            reply = (
                f"Your order is currently {context.order_status}."
                if context.order_status
                else "I can help check the order status once an order is selected."
            )
        return SupportResult(
            reply=reply,
            intent=result.intent,
            confidence=float(result.confidence),
            should_escalate=should_escalate,
            escalation_reason=escalation_reason,
        )
