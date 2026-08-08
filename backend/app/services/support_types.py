from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class SupportIntent(StrEnum):
    ORDER_STATUS = "order_status"
    DELIVERY_ISSUE = "delivery_issue"
    REFUND = "refund"
    CANCELLATION = "cancellation"
    PAYMENT_ISSUE = "payment_issue"
    ACCOUNT_ISSUE = "account_issue"
    GENERAL_QUERY = "general_query"


class AgentAction(StrEnum):
    ANSWER = "ANSWER"
    ASK_CUSTOMER = "ASK_CUSTOMER"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    ESCALATE = "ESCALATE"
    REQUEST_HUMAN_DECISION = "REQUEST_HUMAN_DECISION"


class RecommendedResolution(StrEnum):
    NONE = "NONE"
    INVESTIGATE = "INVESTIGATE"
    REFUND = "REFUND"
    REPLACE = "REPLACE"
    CANCEL = "CANCEL"
    SECURITY_REVIEW = "SECURITY_REVIEW"
    PAYMENT_REVIEW = "PAYMENT_REVIEW"


@dataclass(frozen=True)
class ConversationTurn:
    sender_type: str
    content: str


@dataclass(frozen=True)
class TrustedEvidence:
    source: str
    available: bool
    summary: str
    is_demo: bool = False


@dataclass(frozen=True)
class SupportContext:
    message: str
    customer_name: str | None = None
    order_status: str | None = None
    external_order_id: str | None = None
    product_name: str | None = None
    history: tuple[ConversationTurn, ...] = ()
    trusted_evidence: tuple[TrustedEvidence, ...] = ()
    conversation_status: str | None = None
    escalation_status: str | None = None
    escalation_reason: str | None = None
    human_response: str | None = None


@dataclass(frozen=True)
class RoutingDecision:
    intent: SupportIntent
    confidence: float


@dataclass(frozen=True)
class SupportResult:
    reply: str
    intent: SupportIntent
    confidence: float
    should_escalate: bool
    escalation_reason: str | None = None
    action: AgentAction | None = None
    missing_information: tuple[str, ...] = ()
    evidence_needed: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    recommended_resolution: RecommendedResolution = RecommendedResolution.NONE


@dataclass(frozen=True)
class AgentDecision:
    reply: str
    confidence: float
    action: AgentAction
    missing_information: tuple[str, ...] = ()
    evidence_needed: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()
    recommended_resolution: RecommendedResolution = RecommendedResolution.NONE
    escalation_reason: str | None = None


@dataclass(frozen=True)
class EvidenceAnalysis:
    findings: tuple[str, ...]
    limitations: tuple[str, ...]
    confidence: float
    recommended_resolution: RecommendedResolution


class SupportProvider(Protocol):
    def respond(self, context: SupportContext) -> SupportResult: ...


class RoutingProvider(Protocol):
    def route(self, context: SupportContext) -> RoutingDecision: ...


class SpecialistProvider(Protocol):
    def investigate(
        self,
        intent: SupportIntent,
        context: SupportContext,
        instructions: str,
    ) -> AgentDecision: ...

    def respond_for_intent(
        self,
        intent: SupportIntent,
        context: SupportContext,
        instructions: str,
    ) -> SupportResult: ...
