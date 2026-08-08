import unittest
from decimal import Decimal

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.routes import chat as chat_routes
from app.api.routes.chat import create_chat
from app.api.routes.orders import create_order, get_customer_orders, get_order
from app.db.base import Base
from app.main import app
from app.models import Company, Conversation, Customer, Escalation, Message, Order
from app.schemas.chat import ChatRequest
from app.schemas.orders import OrderCreate
from app.services.support_ai import (
    SupportAIService,
    SupportContext,
    SupportIntent,
    SupportResult,
    SupportTurn,
)


class UnavailableProvider:
    def respond(self, context: SupportContext) -> object:
        raise RuntimeError("provider unavailable")


class UnsafeLowConfidenceProvider:
    def respond(self, context: SupportContext) -> SupportResult:
        return SupportResult(
            reply="Uncertain provider response",
            intent=SupportIntent.GENERAL_QUERY,
            confidence=0.40,
            should_escalate=False,
        )


class RecordingConversationProvider:
    def __init__(self) -> None:
        self.contexts: list[SupportContext] = []

    def respond(self, context: SupportContext) -> SupportResult:
        self.contexts.append(context)
        return SupportResult(
            reply="Thanks. Tell me one more detail about the delivery problem.",
            intent=SupportIntent.DELIVERY_ISSUE,
            confidence=0.90,
            should_escalate=False,
        )


class OrdersChatPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.original_support_ai_service = chat_routes.support_ai_service
        chat_routes.support_ai_service = SupportAIService()
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

        self.company_a = Company(name="ShopX", api_key="shopx-test-key")
        self.company_b = Company(name="OtherCo", api_key="other-test-key")
        self.db.add_all([self.company_a, self.company_b])
        self.db.flush()

        self.customer_a = Customer(
            company_id=self.company_a.id,
            name="ShopX Customer",
            email="customer-a@example.test",
        )
        self.customer_b = Customer(
            company_id=self.company_b.id,
            name="Other Customer",
            email="customer-b@example.test",
        )
        self.db.add_all([self.customer_a, self.customer_b])
        self.db.flush()

        self.order_a = Order(
            company_id=self.company_a.id,
            customer_id=self.customer_a.id,
            external_order_id="SHOPX-EXISTING",
            product_name="Headphones",
            amount=Decimal("99.00"),
            status="processing",
        )
        self.order_b = Order(
            company_id=self.company_b.id,
            customer_id=self.customer_b.id,
            external_order_id="OTHER-EXISTING",
            product_name="Keyboard",
            amount=Decimal("79.00"),
            status="shipped",
        )
        self.db.add_all([self.order_a, self.order_b])
        self.db.commit()

    def tearDown(self) -> None:
        chat_routes.support_ai_service = self.original_support_ai_service
        self.db.close()
        self.engine.dispose()

    def _order_payload(self) -> OrderCreate:
        return OrderCreate(
            customer_id=self.customer_a.id,
            external_order_id="SHOPX-NEW-001",
            product_name="Demo Product",
            amount=Decimal("49.95"),
            status="processing",
        )

    def _chat_payload(
        self,
        message: str = "Where is my order?",
        conversation_id: int | None = None,
    ) -> ChatRequest:
        return ChatRequest(
            customer_id=self.customer_a.id,
            order_id=self.order_a.id,
            conversation_id=conversation_id,
            message=message,
        )

    def test_create_order(self) -> None:
        order = create_order(self._order_payload(), self.db, self.company_a)
        self.assertEqual(order.company_id, self.company_a.id)
        self.assertEqual(order.customer_id, self.customer_a.id)
        self.assertEqual(order.external_order_id, "SHOPX-NEW-001")

    def test_get_order(self) -> None:
        order = get_order(self.order_a.id, self.db, self.company_a)
        self.assertEqual(order.id, self.order_a.id)

    def test_get_customer_orders(self) -> None:
        create_order(self._order_payload(), self.db, self.company_a)
        orders = get_customer_orders(self.customer_a.id, self.db, self.company_a)
        self.assertEqual({order.external_order_id for order in orders}, {
            "SHOPX-EXISTING",
            "SHOPX-NEW-001",
        })

    def test_create_order_rejects_invalid_customer(self) -> None:
        payload = self._order_payload().model_copy(update={"customer_id": 999_999})
        with self.assertRaises(HTTPException) as context:
            create_order(payload, self.db, self.company_a)
        self.assertEqual(context.exception.status_code, 404)

    def test_create_order_rejects_cross_tenant_customer(self) -> None:
        payload = self._order_payload().model_copy(
            update={"customer_id": self.customer_b.id}
        )
        with self.assertRaises(HTTPException) as context:
            create_order(payload, self.db, self.company_a)
        self.assertEqual(context.exception.status_code, 404)

    def test_cross_tenant_order_access_is_hidden(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_order(self.order_b.id, self.db, self.company_a)
        self.assertEqual(context.exception.status_code, 404)

    def test_request_cannot_supply_company_id(self) -> None:
        with self.assertRaises(ValidationError):
            OrderCreate.model_validate(
                {
                    **self._order_payload().model_dump(),
                    "company_id": self.company_b.id,
                }
            )

    def test_create_conversation(self) -> None:
        response = create_chat(self._chat_payload(), self.db, self.company_a)
        conversation = self.db.get(Conversation, response.conversation_id)
        self.assertIsNotNone(conversation)
        self.assertEqual(conversation.company_id, self.company_a.id)
        self.assertEqual(conversation.customer_id, self.customer_a.id)
        self.assertEqual(conversation.order_id, self.order_a.id)

    def test_continue_conversation(self) -> None:
        first = create_chat(self._chat_payload(), self.db, self.company_a)
        second = create_chat(
            self._chat_payload(conversation_id=first.conversation_id),
            self.db,
            self.company_a,
        )
        conversation_count = self.db.scalar(
            select(func.count()).select_from(Conversation).where(
                Conversation.company_id == self.company_a.id
            )
        )
        self.assertEqual(second.conversation_id, first.conversation_id)
        self.assertEqual(conversation_count, 1)

    def test_continued_chat_passes_persisted_history_to_provider(self) -> None:
        provider = RecordingConversationProvider()
        chat_routes.support_ai_service = SupportAIService(provider=provider)

        first = create_chat(
            self._chat_payload(message="My headphones arrived damaged"),
            self.db,
            self.company_a,
        )
        create_chat(
            self._chat_payload(
                message="The outer box looked fine",
                conversation_id=first.conversation_id,
            ),
            self.db,
            self.company_a,
        )

        self.assertEqual(len(provider.contexts), 2)
        second_context = provider.contexts[1]
        self.assertEqual(
            [(turn.sender_type, turn.content) for turn in second_context.history],
            [
                ("CUSTOMER", "My headphones arrived damaged"),
                (
                    "AI",
                    "Thanks. Tell me one more detail about the delivery problem.",
                ),
            ],
        )

    def test_fallback_uses_customer_history_for_short_follow_up(self) -> None:
        service = SupportAIService()
        result = service.respond(
            SupportContext(
                message="The outer box looked fine",
                history=(
                    SupportTurn(
                        sender_type="CUSTOMER",
                        content="My headphones arrived damaged",
                    ),
                    SupportTurn(
                        sender_type="AI",
                        content="Please tell me whether the outer package was damaged.",
                        intent="delivery_issue",
                        confidence=0.90,
                    ),
                ),
            )
        )
        self.assertEqual(result.intent, SupportIntent.DELIVERY_ISSUE)
        self.assertTrue(result.should_escalate)
        self.assertIn("added that detail", result.reply)

    def test_customer_message_is_persisted(self) -> None:
        response = create_chat(self._chat_payload(), self.db, self.company_a)
        customer_message = self.db.scalar(
            select(Message).where(
                Message.conversation_id == response.conversation_id,
                Message.sender_type == "CUSTOMER",
            )
        )
        self.assertIsNotNone(customer_message)
        self.assertEqual(customer_message.content, "Where is my order?")

    def test_ai_message_is_persisted_with_intent_and_confidence(self) -> None:
        response = create_chat(self._chat_payload(), self.db, self.company_a)
        ai_message = self.db.scalar(
            select(Message).where(
                Message.conversation_id == response.conversation_id,
                Message.sender_type == "AI",
            )
        )
        self.assertIsNotNone(ai_message)
        self.assertEqual(ai_message.content, response.reply)
        self.assertEqual(ai_message.intent, response.intent)
        self.assertEqual(ai_message.confidence, response.confidence)

    def test_order_status_intent_and_confidence(self) -> None:
        response = create_chat(self._chat_payload(), self.db, self.company_a)
        self.assertEqual(response.intent, "order_status")
        self.assertEqual(response.confidence, 0.91)
        self.assertFalse(response.should_escalate)
        self.assertIn("processing", response.reply)

    def test_automatic_escalation(self) -> None:
        response = create_chat(
            self._chat_payload(message="I need a refund"),
            self.db,
            self.company_a,
        )
        escalation = self.db.get(Escalation, response.escalation_id)
        conversation = self.db.get(Conversation, response.conversation_id)
        self.assertTrue(response.should_escalate)
        self.assertIsNotNone(escalation)
        self.assertEqual(escalation.company_id, self.company_a.id)
        self.assertEqual(escalation.status, "OPEN")
        self.assertEqual(conversation.status, "ESCALATED")

    def test_no_duplicate_open_escalation(self) -> None:
        first = create_chat(
            self._chat_payload(message="I need a refund"),
            self.db,
            self.company_a,
        )
        second = create_chat(
            self._chat_payload(
                message="I still need a refund",
                conversation_id=first.conversation_id,
            ),
            self.db,
            self.company_a,
        )
        open_count = self.db.scalar(
            select(func.count()).select_from(Escalation).where(
                Escalation.company_id == self.company_a.id,
                Escalation.conversation_id == first.conversation_id,
                Escalation.status == "OPEN",
            )
        )
        self.assertEqual(open_count, 1)
        self.assertEqual(second.escalation_id, first.escalation_id)

    def test_invalid_conversation(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_chat(
                self._chat_payload(conversation_id=999_999),
                self.db,
                self.company_a,
            )
        self.assertEqual(context.exception.status_code, 404)

    def test_cross_tenant_conversation_access_is_hidden(self) -> None:
        other_response = create_chat(
            ChatRequest(
                customer_id=self.customer_b.id,
                order_id=self.order_b.id,
                message="Where is my order?",
            ),
            self.db,
            self.company_b,
        )
        with self.assertRaises(HTTPException) as context:
            create_chat(
                self._chat_payload(conversation_id=other_response.conversation_id),
                self.db,
                self.company_a,
            )
        self.assertEqual(context.exception.status_code, 404)

    def test_cross_tenant_order_cannot_be_attached_to_chat(self) -> None:
        with self.assertRaises(HTTPException) as context:
            create_chat(
                ChatRequest(
                    customer_id=self.customer_a.id,
                    order_id=self.order_b.id,
                    message="Where is my order?",
                ),
                self.db,
                self.company_a,
            )
        self.assertEqual(context.exception.status_code, 404)

    def test_all_new_endpoints_require_api_key_security(self) -> None:
        schema = app.openapi()["paths"]
        operations = (
            schema["/api/v1/orders"]["post"],
            schema["/api/v1/orders/{order_id}"]["get"],
            schema["/api/v1/customers/{customer_id}/orders"]["get"],
            schema["/api/v1/chat"]["post"],
        )
        self.assertTrue(all(operation.get("security") for operation in operations))

    def test_all_intents_are_detected_with_bounded_confidence(self) -> None:
        service = SupportAIService()
        cases = {
            "Where is my order?": SupportIntent.ORDER_STATUS,
            "My delivery is late": SupportIntent.DELIVERY_ISSUE,
            "I need a refund": SupportIntent.REFUND,
            "Cancel my order": SupportIntent.CANCELLATION,
            "My card was charged twice": SupportIntent.PAYMENT_ISSUE,
            "I cannot login to my account": SupportIntent.ACCOUNT_ISSUE,
            "Can somebody help me?": SupportIntent.GENERAL_QUERY,
        }
        for message, expected_intent in cases.items():
            with self.subTest(message=message):
                result = service.respond(SupportContext(message=message))
                self.assertEqual(result.intent, expected_intent)
                self.assertGreaterEqual(result.confidence, 0.0)
                self.assertLessEqual(result.confidence, 1.0)

    def test_unavailable_provider_uses_deterministic_fallback(self) -> None:
        service = SupportAIService(provider=UnavailableProvider())
        result = service.respond(SupportContext(message="Where is my order?"))
        self.assertEqual(result.intent, SupportIntent.ORDER_STATUS)
        self.assertEqual(result.confidence, 0.91)

    def test_provider_cannot_bypass_low_confidence_escalation(self) -> None:
        service = SupportAIService(provider=UnsafeLowConfidenceProvider())
        result = service.respond(SupportContext(message="Unclear request"))
        self.assertTrue(result.should_escalate)
        self.assertIn("Low-confidence", result.escalation_reason)


if __name__ == "__main__":
    unittest.main()
