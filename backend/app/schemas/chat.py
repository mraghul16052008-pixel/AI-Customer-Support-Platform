from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    order_id: int | None = Field(default=None, gt=0)
    conversation_id: int | None = Field(default=None, gt=0)
    message: str = Field(min_length=1, max_length=10_000)

    @field_validator("message")
    @classmethod
    def message_must_contain_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must contain text")
        return value


class ChatResponse(BaseModel):
    conversation_id: int
    reply: str
    intent: str
    confidence: float = Field(ge=0.0, le=1.0)
    should_escalate: bool
    escalation_id: int | None
