import unittest
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.routes.admin import (
    get_admin_analytics,
    get_admin_conversation,
    get_admin_conversations,
    get_admin_escalation,
    get_admin_escalations,
    get_admin_orders,
    update_admin_escalation,
)
from app.db.base import Base
from app.main import app
from app.models import Company, Conversation, Customer, Escalation, Message, Order
from app.schemas.admin import AdminEscalationUpdate


class AdminApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)

        self.company_a = Company(name="ShopX", api_key="shopx-admin-key")
        self.company_b = Company(name="OtherCo", api_key="other-admin-key")
        self.company_empty = Company(name="EmptyCo", api_key="empty-admin-key")
        self.db.add_all([self.company_a, self.company_b, self.company_empty])
        self.db.flush()

        self.customer_a = Customer(
            company_id=self.company_a.id,
            name="ShopX Customer",
            email="shopx-customer@example.test",
        )
        self.customer_b = Customer(
            company_id=self.company_b.id,
            name="Other Customer",
            email="other-customer@example.test",
        )
        self.db.add_all([self.customer_a, self.customer_b])
        self.db.flush()

        self.order_a = Order(
            company_id=self.company_a.id,
            customer_id=self.customer_a.id,
            external_order_id="SHOPX-ADMIN-1",
            product_name="Headphones",
            amount=Decimal("99.00"),
            status="processing",
        )
        self.order_b = Order(
            company_id=self.company_b.id,
            customer_id=self.customer_b.id,
            external_order_id="OTHER-ADMIN-1",
            product_name="Keyboard",
            amount=Decimal("79.00"),
            status="shipped",
        )
        self.db.add_all([self.order_a, self.order_b])
        self.db.flush()

        self.conversation_a = Conversation(
            company_id=self.company_a.id,
            customer_id=self.customer_a.id,
            order_id=self.order_a.id,
            status="ESCALATED",
        )
        self.conversation_a_ai = Conversation(
            company_id=self.company_a.id,
            customer_id=self.customer_a.id,
            order_id=None,
            status="OPEN",
        )
        self.conversation_b = Conversation(
            company_id=self.company_b.id,
            customer_id=self.customer_b.id,
            order_id=self.order_b.id,
            status="ESCALATED",
        )
        self.db.add_all(
            [self.conversation_a, self.conversation_a_ai, self.conversation_b]
        )
        self.db.flush()

        self.db.add_all(
            [
                Message(
                    conversation_id=self.conversation_a.id,
                    sender_type="CUSTOMER",
                    content="I need a refund",
                ),
                Message(
                    conversation_id=self.conversation_a.id,
                    sender_type="AI",
                    content="I will escalate this request.",
                    intent="refund",
                    confidence=0.94,
                ),
                Message(
                    conversation_id=self.conversation_b.id,
                    sender_type="CUSTOMER",
                    content="Other tenant message",
                ),
            ]
        )
        self.escalation_a = Escalation(
            company_id=self.company_a.id,
            conversation_id=self.conversation_a.id,
            reason="Refund request requires human review.",
            status="OPEN",
        )
        self.escalation_b = Escalation(
            company_id=self.company_b.id,
            conversation_id=self.conversation_b.id,
            reason="Other tenant reason.",
            status="OPEN",
        )
        self.db.add_all([self.escalation_a, self.escalation_b])
        self.db.commit()

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_admin_order_list(self) -> None:
        orders = get_admin_orders(self.db, self.company_a)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].id, self.order_a.id)
        self.assertEqual(orders[0].customer.id, self.customer_a.id)
        self.assertNotIn("api_key", orders[0].model_dump())

    def test_conversation_list(self) -> None:
        conversations = get_admin_conversations(self.db, self.company_a)
        self.assertEqual(
            {item.conversation_id for item in conversations},
            {self.conversation_a.id, self.conversation_a_ai.id},
        )
        with_order = next(
            item
            for item in conversations
            if item.conversation_id == self.conversation_a.id
        )
        self.assertEqual(with_order.customer.id, self.customer_a.id)
        self.assertEqual(with_order.order.id, self.order_a.id)

    def test_conversation_details(self) -> None:
        detail = get_admin_conversation(
            self.conversation_a.id, self.db, self.company_a
        )
        self.assertEqual(detail.conversation_id, self.conversation_a.id)
        self.assertEqual(detail.customer.email, self.customer_a.email)
        self.assertEqual(detail.order.external_order_id, self.order_a.external_order_id)

    def test_message_details(self) -> None:
        detail = get_admin_conversation(
            self.conversation_a.id, self.db, self.company_a
        )
        self.assertEqual(len(detail.messages), 2)
        ai_message = next(
            message for message in detail.messages if message.sender_type == "AI"
        )
        self.assertEqual(ai_message.intent, "refund")
        self.assertEqual(ai_message.confidence, 0.94)
        self.assertNotIn("Other tenant", " ".join(m.content for m in detail.messages))

    def test_escalation_list(self) -> None:
        escalations = get_admin_escalations(self.db, self.company_a)
        self.assertEqual(len(escalations), 1)
        self.assertEqual(escalations[0].id, self.escalation_a.id)
        self.assertEqual(escalations[0].conversation.id, self.conversation_a.id)

    def test_escalation_details(self) -> None:
        escalation = get_admin_escalation(
            self.escalation_a.id, self.db, self.company_a
        )
        self.assertEqual(escalation.reason, self.escalation_a.reason)
        self.assertEqual(escalation.status, "OPEN")

    def test_human_assignment(self) -> None:
        escalation = update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(assigned_agent="Agent Priya"),
            self.db,
            self.company_a,
        )
        self.assertEqual(escalation.assigned_agent, "Agent Priya")

    def test_in_progress_transition(self) -> None:
        escalation = update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(status="IN_PROGRESS"),
            self.db,
            self.company_a,
        )
        self.assertEqual(escalation.status, "IN_PROGRESS")
        self.assertIsNone(escalation.resolved_at)
        self.assertEqual(escalation.conversation.status, "ESCALATED")

    def test_human_response(self) -> None:
        escalation = update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(human_response="Your refund has been approved."),
            self.db,
            self.company_a,
        )
        self.assertEqual(escalation.human_response, "Your refund has been approved.")

    def test_resolved_transition_sets_timestamp_and_conversation_status(self) -> None:
        escalation = update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(
                assigned_agent="Agent Priya",
                status="RESOLVED",
                human_response="Resolved for the customer.",
            ),
            self.db,
            self.company_a,
        )
        self.assertEqual(escalation.status, "RESOLVED")
        self.assertIsNotNone(escalation.resolved_at)
        self.assertEqual(escalation.conversation.status, "RESOLVED")

    def test_resolved_escalation_cannot_be_reopened(self) -> None:
        update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(status="RESOLVED"),
            self.db,
            self.company_a,
        )
        with self.assertRaises(HTTPException) as context:
            update_admin_escalation(
                self.escalation_a.id,
                AdminEscalationUpdate(status="OPEN"),
                self.db,
                self.company_a,
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_patch_does_not_create_duplicate_escalation(self) -> None:
        update_admin_escalation(
            self.escalation_a.id,
            AdminEscalationUpdate(status="IN_PROGRESS"),
            self.db,
            self.company_a,
        )
        escalation_count = self.db.scalar(
            select(func.count()).select_from(Escalation).where(
                Escalation.company_id == self.company_a.id,
                Escalation.conversation_id == self.conversation_a.id,
            )
        )
        self.assertEqual(escalation_count, 1)

    def test_analytics(self) -> None:
        analytics = get_admin_analytics(self.db, self.company_a)
        self.assertEqual(analytics.total_conversations, 2)
        self.assertEqual(analytics.human_escalated, 1)
        self.assertEqual(analytics.ai_resolved, 1)
        self.assertEqual(analytics.open_escalations, 1)
        self.assertEqual(analytics.resolution_rate, 50.0)

    def test_zero_conversation_analytics(self) -> None:
        analytics = get_admin_analytics(self.db, self.company_empty)
        self.assertEqual(
            analytics.model_dump(),
            {
                "total_conversations": 0,
                "ai_resolved": 0,
                "human_escalated": 0,
                "open_escalations": 0,
                "resolution_rate": 0.0,
            },
        )

    def test_cross_tenant_isolation(self) -> None:
        orders = get_admin_orders(self.db, self.company_a)
        self.assertNotIn(self.order_b.id, {order.id for order in orders})

        with self.assertRaises(HTTPException) as conversation_context:
            get_admin_conversation(
                self.conversation_b.id, self.db, self.company_a
            )
        self.assertEqual(conversation_context.exception.status_code, 404)

        with self.assertRaises(HTTPException) as escalation_context:
            get_admin_escalation(self.escalation_b.id, self.db, self.company_a)
        self.assertEqual(escalation_context.exception.status_code, 404)

        with self.assertRaises(HTTPException) as patch_context:
            update_admin_escalation(
                self.escalation_b.id,
                AdminEscalationUpdate(status="RESOLVED"),
                self.db,
                self.company_a,
            )
        self.assertEqual(patch_context.exception.status_code, 404)

    def test_invalid_escalation(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_admin_escalation(999_999, self.db, self.company_a)
        self.assertEqual(context.exception.status_code, 404)

    def test_invalid_conversation(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_admin_conversation(999_999, self.db, self.company_a)
        self.assertEqual(context.exception.status_code, 404)

    def test_admin_routes_require_api_key_and_existing_routes_remain(self) -> None:
        schema = app.openapi()["paths"]
        admin_operations = (
            schema["/api/v1/admin/orders"]["get"],
            schema["/api/v1/admin/conversations"]["get"],
            schema["/api/v1/admin/conversations/{conversation_id}"]["get"],
            schema["/api/v1/admin/escalations"]["get"],
            schema["/api/v1/admin/escalations/{escalation_id}"]["get"],
            schema["/api/v1/admin/escalations/{escalation_id}"]["patch"],
            schema["/api/v1/admin/analytics"]["get"],
        )
        self.assertTrue(all(operation.get("security") for operation in admin_operations))
        for path in (
            "/api/v1/health",
            "/api/v1/health/db",
            "/api/v1/company/me",
            "/api/v1/orders",
            "/api/v1/chat",
        ):
            self.assertIn(path, schema)


if __name__ == "__main__":
    unittest.main()
