from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company
from app.db.session import get_db
from app.models import Company, Conversation, Customer, Escalation, Message, Order
from app.schemas.chat import ChatRequest, ChatResponse, EvidenceUploadResponse
from app.services import SupportContext, support_ai_service
from app.services.evidence import (
    MAX_EVIDENCE_BYTES,
    MAX_EVIDENCE_PER_CONVERSATION,
    safe_filename,
    validate_image,
)
from app.services.support_types import ConversationTurn

router = APIRouter()
HISTORY_LIMIT = 12


def _history(db: Session, company_id: int, conversation_id: int) -> tuple[ConversationTurn, ...]:
    rows = db.execute(
        select(Message.sender_type, Message.content)
        .join(Conversation, Conversation.id == Message.conversation_id)
        .where(
            Conversation.company_id == company_id,
            Message.conversation_id == conversation_id,
        )
        .order_by(Message.id.desc())
        .limit(HISTORY_LIMIT)
    ).all()
    return tuple(ConversationTurn(sender, content) for sender, content in reversed(rows))


def _customer(db: Session, company_id: int, customer_id: int) -> Customer:
    value = db.scalar(select(Customer).where(Customer.id == customer_id, Customer.company_id == company_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return value


def _order(db: Session, company_id: int, customer_id: int, order_id: int | None) -> Order | None:
    if order_id is None:
        return None
    value = db.scalar(select(Order).where(Order.id == order_id, Order.company_id == company_id, Order.customer_id == customer_id))
    if value is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return value


def _conversation(db: Session, company_id: int, customer_id: int, conversation_id: int) -> Conversation:
    value = db.scalar(select(Conversation).where(
        Conversation.id == conversation_id,
        Conversation.company_id == company_id,
        Conversation.customer_id == customer_id,
    ))
    if value is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return value


def _latest_escalation(
    db: Session, company_id: int, conversation_id: int
) -> Escalation | None:
    return db.scalar(
        select(Escalation)
        .join(Conversation, Conversation.id == Escalation.conversation_id)
        .where(
            Escalation.company_id == company_id,
            Escalation.conversation_id == conversation_id,
            Conversation.company_id == company_id,
        )
        .order_by(Escalation.id.desc())
        .limit(1)
    )


def _context(
    message: str,
    customer: Customer,
    order: Order | None,
    history: tuple[ConversationTurn, ...],
    conversation: Conversation | None = None,
    escalation: Escalation | None = None,
) -> SupportContext:
    return SupportContext(
        message=message,
        customer_name=customer.name,
        order_status=order.status if order else None,
        external_order_id=order.external_order_id if order else None,
        product_name=order.product_name if order else None,
        history=history,
        conversation_status=conversation.status if conversation else None,
        escalation_status=escalation.status if escalation else None,
        escalation_reason=escalation.reason if escalation else None,
        human_response=escalation.human_response if escalation else None,
    )


def _open_escalation(db: Session, company_id: int, conversation_id: int, reason: str) -> Escalation:
    value = db.scalar(select(Escalation).where(
        Escalation.company_id == company_id,
        Escalation.conversation_id == conversation_id,
        Escalation.status.in_(("OPEN", "IN_PROGRESS")),
    ))
    if value is None:
        value = Escalation(company_id=company_id, conversation_id=conversation_id, reason=reason, status="OPEN")
        db.add(value)
        db.flush()
    elif reason not in value.reason:
        value.reason = f"{value.reason}\n\nLatest investigation: {reason}"[-4_000:]
    return value


def _investigation_reason(
    default_reason: str, context: SupportContext, result: object
) -> str:
    confidence = float(getattr(result, "confidence", 0.0))
    details = [default_reason, f"Confidence: {confidence:.2f}."]
    if context.customer_name:
        details.append(f"Customer: {context.customer_name}.")
    order_summary = ", ".join(
        value
        for value in (
            f"order {context.external_order_id}" if context.external_order_id else None,
            context.product_name,
            f"trusted status {context.order_status}" if context.order_status else None,
        )
        if value
    )
    if order_summary:
        details.append(f"Order context: {order_summary}.")
    findings = getattr(result, "findings", ())
    missing_information = getattr(result, "missing_information", ())
    evidence_needed = getattr(result, "evidence_needed", ())
    recommendation = getattr(result, "recommended_resolution", None)
    if findings:
        details.append("Findings: " + "; ".join(findings) + ".")
    if missing_information:
        details.append("Missing information: " + "; ".join(missing_information) + ".")
    if evidence_needed:
        details.append("Evidence requested: " + "; ".join(evidence_needed) + ".")
    if recommendation and recommendation.value != "NONE":
        details.append(
            f"AI recommendation: {recommendation.value}; human approval required."
        )
    return " ".join(details)


@router.post("/chat", response_model=ChatResponse)
def create_chat(
    payload: ChatRequest,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> ChatResponse:
    customer = _customer(db, current_company.id, payload.customer_id)
    requested_order = _order(db, current_company.id, customer.id, payload.order_id)
    if payload.conversation_id is None:
        conversation = Conversation(
            company_id=current_company.id, customer_id=customer.id,
            order_id=requested_order.id if requested_order else None, status="OPEN",
        )
        db.add(conversation)
        db.flush()
    else:
        conversation = _conversation(db, current_company.id, customer.id, payload.conversation_id)
        if requested_order is not None:
            if conversation.order_id is None:
                conversation.order_id = requested_order.id
            elif conversation.order_id != requested_order.id:
                raise HTTPException(status_code=400, detail="Order does not match this conversation")

    order = requested_order or _order(db, current_company.id, customer.id, conversation.order_id)
    history = _history(db, current_company.id, conversation.id)
    current_escalation = _latest_escalation(db, current_company.id, conversation.id)
    db.add(Message(conversation_id=conversation.id, sender_type="CUSTOMER", content=payload.message))
    support_context = _context(
        payload.message, customer, order, history, conversation, current_escalation
    )
    result = support_ai_service.respond(support_context)
    db.add(Message(
        conversation_id=conversation.id, sender_type="AI", content=result.reply,
        intent=result.intent.value, confidence=result.confidence,
    ))
    conversation.updated_at = datetime.now(timezone.utc)
    escalation = None
    if result.should_escalate:
        escalation = _open_escalation(
            db, current_company.id, conversation.id,
            _investigation_reason(
                result.escalation_reason or "Support review required.",
                support_context,
                result,
            ),
        )
        conversation.status = "ESCALATED"
    db.commit()
    return ChatResponse(
        conversation_id=conversation.id, reply=result.reply,
        intent=result.intent.value, confidence=result.confidence,
        should_escalate=result.should_escalate,
        escalation_id=escalation.id if escalation else None,
    )


@router.post("/chat/evidence", response_model=EvidenceUploadResponse)
async def upload_chat_evidence(
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
    customer_id: Annotated[int, Form(gt=0)],
    conversation_id: Annotated[int, Form(gt=0)],
    file: Annotated[UploadFile, File()],
    order_id: Annotated[int | None, Form(gt=0)] = None,
) -> EvidenceUploadResponse:
    customer = _customer(db, current_company.id, customer_id)
    conversation = _conversation(db, current_company.id, customer.id, conversation_id)
    order = _order(db, current_company.id, customer.id, order_id or conversation.order_id)
    if order_id is not None and conversation.order_id != order_id:
        raise HTTPException(status_code=400, detail="Order does not match this conversation")
    evidence_count = db.scalar(
        select(func.count(Message.id)).join(Conversation).where(
            Conversation.company_id == current_company.id,
            Message.conversation_id == conversation.id,
            Message.sender_type == "CUSTOMER_EVIDENCE",
        )
    ) or 0
    if evidence_count >= MAX_EVIDENCE_PER_CONVERSATION:
        raise HTTPException(status_code=400, detail="Evidence upload limit reached for this conversation")
    content = await file.read(MAX_EVIDENCE_BYTES + 1)
    try:
        media_type = validate_image(content, file.content_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    context = _context(
        "Customer uploaded delivery evidence.", customer, order,
        _history(db, current_company.id, conversation.id),
        conversation,
        _latest_escalation(db, current_company.id, conversation.id),
    )
    analysis = support_ai_service.analyze_evidence(context, content, media_type)
    name = safe_filename(file.filename)
    findings = "; ".join(analysis.findings) or "No reliable visual finding."
    limitations = "; ".join(analysis.limitations) or "Human verification required."
    db.add(Message(
        conversation_id=conversation.id,
        sender_type="CUSTOMER_EVIDENCE",
        content=(
            f"Customer-supplied evidence: {name} ({media_type}, {len(content)} bytes). "
            f"Automated findings: {findings} Limitations: {limitations} "
            "This is not trusted ShopX fulfillment evidence."
        ),
    ))
    reply = (
        f"I received the customer-supplied image. The cautious visual review found: {findings} "
        "No trusted ShopX packing evidence is available for comparison. "
        f"The non-binding recommendation is {analysis.recommended_resolution.value.lower()}; "
        "a human support agent must make the final decision."
    )
    db.add(Message(
        conversation_id=conversation.id, sender_type="AI", content=reply,
        intent="delivery_issue", confidence=analysis.confidence,
    ))
    reason = (
        f"Customer evidence received. Findings: {findings} Recommendation: "
        f"{analysis.recommended_resolution.value}. No trusted packing evidence is available. "
        "Human approval required."
    )
    escalation = _open_escalation(db, current_company.id, conversation.id, reason)
    escalation.reason = reason
    conversation.status = "ESCALATED"
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    return EvidenceUploadResponse(
        conversation_id=conversation.id, reply=reply,
        evidence_count=evidence_count + 1, confidence=analysis.confidence,
        recommended_resolution=analysis.recommended_resolution.value,
        escalation_id=escalation.id,
    )
