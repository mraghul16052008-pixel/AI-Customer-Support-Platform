from dataclasses import dataclass
from typing import Any

from app.services.support_types import (
    RoutingDecision,
    RoutingProvider,
    SupportContext,
    SupportIntent,
)


@dataclass(frozen=True)
class RoutingOutcome:
    decision: RoutingDecision
    provider_attempted: bool
    provider_succeeded: bool
    fallback_used: bool
    error_type: str | None = None
    error_code: str | int | None = None
    error_status: str | None = None


class DeterministicIntentRouter:
    def route(self, context: SupportContext) -> RoutingDecision:
        text = context.message.casefold()
        if any(term in text for term in ("refund", "money back", "return")):
            return RoutingDecision(SupportIntent.REFUND, 0.94)
        if any(term in text for term in ("charged", "payment", "card", "billing")):
            return RoutingDecision(SupportIntent.PAYMENT_ISSUE, 0.92)
        if any(term in text for term in ("cancel", "cancellation")):
            return RoutingDecision(SupportIntent.CANCELLATION, 0.93)
        if any(
            term in text
            for term in (
                "late",
                "delayed",
                "not arrived",
                "not delivered",
                "damaged",
                "lost",
                "delivery",
                "wrong item",
                "wrong product",
                "incorrect item",
                "replacement",
                "replace",
            )
        ):
            return RoutingDecision(SupportIntent.DELIVERY_ISSUE, 0.90)
        if any(
            term in text
            for term in ("where is my order", "order status", "track", "tracking")
        ):
            return RoutingDecision(SupportIntent.ORDER_STATUS, 0.91)
        if any(
            term in text
            for term in (
                "account",
                "login",
                "log in",
                "password",
                "sign in",
                "hacked",
                "unauthorized",
                "stolen",
                "suspicious",
            )
        ):
            return RoutingDecision(SupportIntent.ACCOUNT_ISSUE, 0.87)
        return RoutingDecision(SupportIntent.GENERAL_QUERY, 0.55)


class IntentRouter:
    def __init__(self, provider: RoutingProvider | None = None) -> None:
        self.provider = provider
        self.fallback = DeterministicIntentRouter()

    def route(self, context: SupportContext) -> RoutingOutcome:
        if self.provider is None:
            return RoutingOutcome(
                decision=self.fallback.route(context),
                provider_attempted=False,
                provider_succeeded=False,
                fallback_used=True,
            )
        try:
            decision = self.provider.route(context)
            self._validate(decision)
            return RoutingOutcome(
                decision=decision,
                provider_attempted=True,
                provider_succeeded=True,
                fallback_used=False,
            )
        except Exception as exc:
            return RoutingOutcome(
                decision=self.fallback.route(context),
                provider_attempted=True,
                provider_succeeded=False,
                fallback_used=True,
                error_type=type(exc).__name__,
                error_code=self._safe_error_value(getattr(exc, "code", None)),
                error_status=self._safe_status(getattr(exc, "status", None)),
            )

    @staticmethod
    def _validate(decision: RoutingDecision) -> None:
        if not isinstance(decision.intent, SupportIntent):
            raise ValueError("Router returned an unsupported intent.")
        if not isinstance(decision.confidence, (int, float)):
            raise ValueError("Router confidence must be numeric.")
        if not 0.0 <= decision.confidence <= 1.0:
            raise ValueError("Router confidence must be between 0 and 1.")

    @staticmethod
    def _safe_error_value(value: Any) -> str | int | None:
        return value if isinstance(value, (str, int)) else None

    @staticmethod
    def _safe_status(value: Any) -> str | None:
        return str(value) if value is not None else None
