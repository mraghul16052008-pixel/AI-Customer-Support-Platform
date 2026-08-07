from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AdminCustomer(BaseModel):
    id: int
    name: str
    email: str


class AdminOrder(BaseModel):
    id: int
    external_order_id: str
    customer: AdminCustomer
    product_name: str
    amount: Decimal
    status: str
    created_at: datetime


class AdminConversationOrder(BaseModel):
    id: int
    external_order_id: str
    product_name: str
    status: str


class AdminConversationSummary(BaseModel):
    conversation_id: int
    customer: AdminCustomer
    order: AdminConversationOrder | None
    status: str
    created_at: datetime
    updated_at: datetime


class AdminMessage(BaseModel):
    id: int
    sender_type: str
    content: str
    intent: str | None
    confidence: float | None
    created_at: datetime


class AdminConversationDetail(AdminConversationSummary):
    messages: list[AdminMessage]


class AdminEscalationConversation(BaseModel):
    id: int
    status: str


class AdminEscalation(BaseModel):
    id: int
    conversation: AdminEscalationConversation
    reason: str
    status: str
    assigned_agent: str | None
    human_response: str | None
    created_at: datetime
    resolved_at: datetime | None


class AdminEscalationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assigned_agent: str | None = Field(default=None, max_length=255)
    status: Literal["OPEN", "IN_PROGRESS", "RESOLVED"] | None = None
    human_response: str | None = None

    @field_validator("assigned_agent", "human_response")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class AdminAnalytics(BaseModel):
    total_conversations: int
    ai_resolved: int
    human_escalated: int
    open_escalations: int
    resolution_rate: float
