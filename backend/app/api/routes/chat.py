from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company
from app.db.session import get_db
from app.models import Company, Conversation, Customer, Escalation, Message, Order
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import SupportContext, support_ai_service


router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def create_chat(
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> ChatResponse:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == payload.customer_id,
            Customer.company_id == current_company.id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")

    requested_order = None
    if payload.order_id is not None:
        requested_order = db.scalar(
            select(Order).where(
                Order.id == payload.order_id,
                Order.company_id == current_company.id,
                Order.customer_id == customer.id,
            )
        )
        if requested_order is None:
            raise HTTPException(status_code=404, detail="Order not found")

    if payload.conversation_id is None:
        conversation = Conversation(
            company_id=current_company.id,
            customer_id=customer.id,
            order_id=requested_order.id if requested_order is not None else None,
            status="OPEN",
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = db.scalar(
            select(Conversation).where(
                Conversation.id == payload.conversation_id,
                Conversation.company_id == current_company.id,
                Conversation.customer_id == customer.id,
            )
        )
        if conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if requested_order is not None:
            if conversation.order_id is None:
                conversation.order_id = requested_order.id
            elif conversation.order_id != requested_order.id:
                raise HTTPException(
                    status_code=400,
                    detail="Order does not match this conversation",
                )

    order = requested_order
    if order is None and conversation.order_id is not None:
        order = db.scalar(
            select(Order).where(
                Order.id == conversation.order_id,
                Order.company_id == current_company.id,
                Order.customer_id == customer.id,
            )
        )
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found")

    customer_message = Message(
        conversation_id=conversation.id,
        sender_type="CUSTOMER",
        content=payload.message,
    )
    db.add(customer_message)

    result = support_ai_service.respond(
        SupportContext(
            message=payload.message,
            customer_name=customer.name,
            order_status=order.status if order is not None else None,
            external_order_id=(
                order.external_order_id if order is not None else None
            ),
            product_name=order.product_name if order is not None else None,
        )
    )
    ai_message = Message(
        conversation_id=conversation.id,
        sender_type="AI",
        content=result.reply,
        intent=result.intent.value,
        confidence=result.confidence,
    )
    db.add(ai_message)
    conversation.updated_at = datetime.now(timezone.utc)

    escalation = None
    if result.should_escalate:
        escalation = db.scalar(
            select(Escalation).where(
                Escalation.company_id == current_company.id,
                Escalation.conversation_id == conversation.id,
                Escalation.status == "OPEN",
            )
        )
        if escalation is None:
            escalation = Escalation(
                company_id=current_company.id,
                conversation_id=conversation.id,
                reason=result.escalation_reason or "Support review required.",
                status="OPEN",
            )
            db.add(escalation)
            db.flush()
        conversation.status = "ESCALATED"

    db.commit()
    return ChatResponse(
        conversation_id=conversation.id,
        reply=result.reply,
        intent=result.intent.value,
        confidence=result.confidence,
        should_escalate=result.should_escalate,
        escalation_id=escalation.id if escalation is not None else None,
    )
