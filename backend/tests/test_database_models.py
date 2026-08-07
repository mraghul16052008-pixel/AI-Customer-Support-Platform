import unittest
from unittest.mock import patch

from fastapi import HTTPException
from sqlalchemy import inspect

from app.api.dependencies.auth import get_current_company
from app.db.base import Base
from app.db.init_db import init_db
from app.models import Company, Conversation, Customer, Escalation, Message, Order


class FakeSession:
    def __init__(self, company: Company | None) -> None:
        self.company = company

    def scalar(self, statement: object) -> Company | None:
        return self.company


class DatabaseModelTests(unittest.TestCase):
    def test_expected_tables_are_registered(self) -> None:
        self.assertEqual(
            set(Base.metadata.tables),
            {
                "companies",
                "customers",
                "orders",
                "conversations",
                "messages",
                "escalations",
            },
        )

    def test_tenant_owned_tables_have_company_id(self) -> None:
        for model in (Customer, Order, Conversation, Escalation):
            self.assertIn("company_id", inspect(model).columns)

    def test_required_relationships_are_configured(self) -> None:
        expected = {
            Company: {"customers", "orders", "conversations", "escalations"},
            Customer: {"company", "orders", "conversations"},
            Order: {"company", "customer", "conversations"},
            Conversation: {
                "company",
                "customer",
                "order",
                "messages",
                "escalations",
            },
            Message: {"conversation"},
            Escalation: {"company", "conversation"},
        }
        for model, relationships in expected.items():
            self.assertEqual(set(inspect(model).relationships.keys()), relationships)

    def test_nullable_columns(self) -> None:
        self.assertTrue(inspect(Conversation).columns.order_id.nullable)
        self.assertTrue(inspect(Message).columns.intent.nullable)
        self.assertTrue(inspect(Message).columns.confidence.nullable)
        self.assertTrue(inspect(Escalation).columns.assigned_agent.nullable)
        self.assertTrue(inspect(Escalation).columns.human_response.nullable)
        self.assertTrue(inspect(Escalation).columns.resolved_at.nullable)

    def test_api_key_identifies_company(self) -> None:
        company = Company(name="ShopX", api_key="test-key")
        self.assertIs(
            get_current_company(api_key="test-key", db=FakeSession(company)), company
        )

    def test_invalid_api_key_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_current_company(api_key="invalid", db=FakeSession(None))
        self.assertEqual(context.exception.status_code, 401)

    @patch("app.db.init_db.Base.metadata.create_all")
    @patch("app.db.init_db.settings.db_password")
    def test_init_db_uses_create_all(self, password: object, create_all: object) -> None:
        password.get_secret_value.return_value = "configured"  # type: ignore[attr-defined]
        init_db()
        create_all.assert_called_once()  # type: ignore[attr-defined]

    @patch("app.db.init_db.Base.metadata.create_all")
    @patch("app.db.init_db.settings.db_password")
    def test_init_db_requires_password(self, password: object, create_all: object) -> None:
        password.get_secret_value.return_value = ""  # type: ignore[attr-defined]
        with self.assertRaisesRegex(RuntimeError, "DB_PASSWORD is not set"):
            init_db()
        create_all.assert_not_called()  # type: ignore[attr-defined]


if __name__ == "__main__":
    unittest.main()
