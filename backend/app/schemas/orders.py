from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class OrderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    external_order_id: str = Field(min_length=1, max_length=255)
    product_name: str = Field(min_length=1, max_length=255)
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    status: str = Field(min_length=1, max_length=50)


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    external_order_id: str
    product_name: str
    amount: Decimal
    status: str
    created_at: datetime
