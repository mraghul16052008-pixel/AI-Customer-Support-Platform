import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.api.dependencies.auth import get_current_company
from app.api.routes.company import get_company_me
from app.db.base import Base
from app.db.seed_demo import (
    DEMO_COMPANY_NAME,
    DEMO_CUSTOMER_EMAIL,
    seed_demo,
)
from app.main import app
from app.models import Company, Customer


class AuthSession:
    def __init__(self, company: Company | None) -> None:
        self.company = company

    def scalar(self, statement: object) -> Company | None:
        return self.company


class CompanyApiAndSeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    def test_valid_api_key_returns_company(self) -> None:
        company = Company(id=1, name="ShopX", api_key="demo-test-key")
        result = get_current_company(
            api_key="demo-test-key", db=AuthSession(company)
        )
        self.assertIs(result, company)

    def test_invalid_api_key_returns_401(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_current_company(api_key="invalid", db=AuthSession(None))
        self.assertEqual(context.exception.status_code, 401)

    def test_missing_api_key_returns_401(self) -> None:
        with self.assertRaises(HTTPException) as context:
            get_current_company(api_key=None, db=AuthSession(None))
        self.assertEqual(context.exception.status_code, 401)

    def test_company_me_does_not_expose_api_key(self) -> None:
        company = Company(id=1, name="ShopX", api_key="must-not-leak")
        response = get_company_me(current_company=company)
        self.assertEqual(response, {"id": 1, "name": "ShopX"})
        self.assertNotIn("api_key", response)

    def test_company_me_route_is_registered(self) -> None:
        self.assertIn("/api/v1/company/me", app.openapi()["paths"])

    def test_shopx_seed_is_idempotent(self) -> None:
        first_company, first_customer = seed_demo(self.session, "demo-test-key")
        second_company, second_customer = seed_demo(self.session, "demo-test-key")

        company_count = self.session.scalar(
            select(func.count()).select_from(Company).where(
                Company.name == DEMO_COMPANY_NAME
            )
        )
        customer_count = self.session.scalar(
            select(func.count()).select_from(Customer).where(
                Customer.company_id == first_company.id,
                Customer.email == DEMO_CUSTOMER_EMAIL,
            )
        )

        self.assertEqual(first_company.id, second_company.id)
        self.assertEqual(first_customer.id, second_customer.id)
        self.assertEqual(company_count, 1)
        self.assertEqual(customer_count, 1)

    def test_shopx_seed_updates_existing_company_key(self) -> None:
        company, _ = seed_demo(self.session, "old-demo-key")
        updated_company, _ = seed_demo(self.session, "new-demo-key")
        self.assertEqual(company.id, updated_company.id)
        self.assertEqual(updated_company.api_key, "new-demo-key")


if __name__ == "__main__":
    unittest.main()
