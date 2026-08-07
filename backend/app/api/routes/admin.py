from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import and_, distinct, func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company
from app.db.session import get_db
from app.models import Company, Conversation, Customer, Escalation, Message, Order
from app.schemas.admin import (
    AdminAnalytics,
    AdminConversationDetail,
    AdminConversationOrder,
    AdminConversationSummary,
    AdminCustomer,
    AdminEscalation,
    AdminEscalationConversation,
    AdminEscalationUpdate,
    AdminMessage,
    AdminOrder,
)


router = APIRouter(prefix="/admin")


def _customer_response(customer: Customer) -> AdminCustomer:
    return AdminCustomer(id=customer.id, name=customer.name, email=customer.email)


def _conversation_order_response(order: Order | None) -> AdminConversationOrder | None:
    if order is None:
        return None
    return AdminConversationOrder(
        id=order.id,
        external_order_id=order.external_order_id,
        product_name=order.product_name,
        status=order.status,
    )


def _conversation_summary_response(
    conversation: Conversation, customer: Customer, order: Order | None
) -> AdminConversationSummary:
    return AdminConversationSummary(
        conversation_id=conversation.id,
        customer=_customer_response(customer),
        order=_conversation_order_response(order),
        status=conversation.status,
        created_at=conversation.created_at,
        updated_at=conversation.updated_at,
    )


def _escalation_response(
    escalation: Escalation, conversation: Conversation
) -> AdminEscalation:
    return AdminEscalation(
        id=escalation.id,
        conversation=AdminEscalationConversation(
            id=conversation.id, status=conversation.status
        ),
        reason=escalation.reason,
        status=escalation.status,
        assigned_agent=escalation.assigned_agent,
        human_response=escalation.human_response,
        created_at=escalation.created_at,
        resolved_at=escalation.resolved_at,
    )


def _conversation_row(
    db: Session, company_id: int, conversation_id: int
) -> tuple[Conversation, Customer, Order | None]:
    row = db.execute(
        select(Conversation, Customer, Order)
        .join(
            Customer,
            and_(
                Customer.id == Conversation.customer_id,
                Customer.company_id == company_id,
            ),
        )
        .outerjoin(
            Order,
            and_(
                Order.id == Conversation.order_id,
                Order.company_id == company_id,
                Order.customer_id == Customer.id,
            ),
        )
        .where(
            Conversation.id == conversation_id,
            Conversation.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row[0], row[1], row[2]


def _escalation_row(
    db: Session, company_id: int, escalation_id: int
) -> tuple[Escalation, Conversation]:
    row = db.execute(
        select(Escalation, Conversation)
        .join(
            Conversation,
            and_(
                Conversation.id == Escalation.conversation_id,
                Conversation.company_id == company_id,
            ),
        )
        .where(
            Escalation.id == escalation_id,
            Escalation.company_id == company_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Escalation not found")
    return row[0], row[1]


@router.get("/orders", response_model=list[AdminOrder])
def get_admin_orders(
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> list[AdminOrder]:
    rows = db.execute(
        select(Order, Customer)
        .join(
            Customer,
            and_(
                Customer.id == Order.customer_id,
                Customer.company_id == current_company.id,
            ),
        )
        .where(Order.company_id == current_company.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
    ).all()
    return [
        AdminOrder(
            id=order.id,
            external_order_id=order.external_order_id,
            customer=_customer_response(customer),
            product_name=order.product_name,
            amount=order.amount,
            status=order.status,
            created_at=order.created_at,
        )
        for order, customer in rows
    ]


@router.get("/conversations", response_model=list[AdminConversationSummary])
def get_admin_conversations(
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> list[AdminConversationSummary]:
    rows = db.execute(
        select(Conversation, Customer, Order)
        .join(
            Customer,
            and_(
                Customer.id == Conversation.customer_id,
                Customer.company_id == current_company.id,
            ),
        )
        .outerjoin(
            Order,
            and_(
                Order.id == Conversation.order_id,
                Order.company_id == current_company.id,
                Order.customer_id == Customer.id,
            ),
        )
        .where(Conversation.company_id == current_company.id)
        .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
    ).all()
    return [
        _conversation_summary_response(conversation, customer, order)
        for conversation, customer, order in rows
    ]


@router.get(
    "/conversations/{conversation_id}", response_model=AdminConversationDetail
)
def get_admin_conversation(
    conversation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> AdminConversationDetail:
    conversation, customer, order = _conversation_row(
        db, current_company.id, conversation_id
    )
    messages = db.scalars(
        select(Message)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Message.conversation_id == conversation.id,
            Conversation.company_id == current_company.id,
        )
        .order_by(Message.created_at, Message.id)
    ).all()
    summary = _conversation_summary_response(conversation, customer, order)
    return AdminConversationDetail(
        **summary.model_dump(),
        messages=[
            AdminMessage(
                id=message.id,
                sender_type=message.sender_type,
                content=message.content,
                intent=message.intent,
                confidence=message.confidence,
                created_at=message.created_at,
            )
            for message in messages
        ],
    )


@router.get("/escalations", response_model=list[AdminEscalation])
def get_admin_escalations(
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> list[AdminEscalation]:
    rows = db.execute(
        select(Escalation, Conversation)
        .join(
            Conversation,
            and_(
                Conversation.id == Escalation.conversation_id,
                Conversation.company_id == current_company.id,
            ),
        )
        .where(Escalation.company_id == current_company.id)
        .order_by(Escalation.created_at.desc(), Escalation.id.desc())
    ).all()
    return [
        _escalation_response(escalation, conversation)
        for escalation, conversation in rows
    ]


@router.get("/escalations/{escalation_id}", response_model=AdminEscalation)
def get_admin_escalation(
    escalation_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> AdminEscalation:
    escalation, conversation = _escalation_row(
        db, current_company.id, escalation_id
    )
    return _escalation_response(escalation, conversation)


@router.patch("/escalations/{escalation_id}", response_model=AdminEscalation)
def update_admin_escalation(
    escalation_id: int,
    payload: AdminEscalationUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> AdminEscalation:
    if not payload.model_fields_set:
        raise HTTPException(status_code=400, detail="No update fields provided")

    escalation, conversation = _escalation_row(
        db, current_company.id, escalation_id
    )
    requested_status = payload.status
    if "status" in payload.model_fields_set and requested_status is None:
        raise HTTPException(status_code=400, detail="Status cannot be null")
    if (
        escalation.status == "RESOLVED"
        and requested_status is not None
        and requested_status != "RESOLVED"
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolved escalations cannot be reopened",
        )

    if "assigned_agent" in payload.model_fields_set:
        escalation.assigned_agent = payload.assigned_agent
    if "human_response" in payload.model_fields_set:
        escalation.human_response = payload.human_response
    if requested_status is not None:
        escalation.status = requested_status
        if requested_status == "RESOLVED":
            escalation.resolved_at = escalation.resolved_at or datetime.now(timezone.utc)
            conversation.status = "RESOLVED"
        else:
            escalation.resolved_at = None
            conversation.status = "ESCALATED"

    db.commit()
    return _escalation_response(escalation, conversation)


@router.get("/analytics", response_model=AdminAnalytics)
def get_admin_analytics(
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> AdminAnalytics:
    total_conversations = db.scalar(
        select(func.count())
        .select_from(Conversation)
        .where(Conversation.company_id == current_company.id)
    ) or 0
    human_escalated = db.scalar(
        select(func.count(distinct(Escalation.conversation_id)))
        .select_from(Escalation)
        .join(
            Conversation,
            and_(
                Conversation.id == Escalation.conversation_id,
                Conversation.company_id == current_company.id,
            ),
        )
        .where(Escalation.company_id == current_company.id)
    ) or 0
    open_escalations = db.scalar(
        select(func.count())
        .select_from(Escalation)
        .join(
            Conversation,
            and_(
                Conversation.id == Escalation.conversation_id,
                Conversation.company_id == current_company.id,
            ),
        )
        .where(
            Escalation.company_id == current_company.id,
            Escalation.status != "RESOLVED",
        )
    ) or 0
    ai_resolved = max(total_conversations - human_escalated, 0)
    resolution_rate = (
        round((ai_resolved / total_conversations) * 100, 2)
        if total_conversations
        else 0.0
    )
    return AdminAnalytics(
        total_conversations=total_conversations,
        ai_resolved=ai_resolved,
        human_escalated=human_escalated,
        open_escalations=open_escalations,
        resolution_rate=resolution_rate,
    )
