from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models import Company, Customer


DEMO_COMPANY_NAME = "ShopX"
DEMO_CUSTOMER_NAME = "Demo Customer"
DEMO_CUSTOMER_EMAIL = "demo@shopx.local"


def seed_demo(session: Session, api_key: str) -> tuple[Company, Customer]:
    if not api_key:
        raise ValueError("A non-empty demo API key is required.")

    key_owner = session.scalar(select(Company).where(Company.api_key == api_key))
    company = session.scalar(
        select(Company)
        .where(Company.name == DEMO_COMPANY_NAME)
        .order_by(Company.id)
        .limit(1)
    )

    if key_owner is not None and key_owner is not company:
        raise ValueError("DEMO_COMPANY_API_KEY is already assigned to another company.")

    if company is None:
        company = Company(name=DEMO_COMPANY_NAME, api_key=api_key)
        session.add(company)
        session.flush()
    elif company.api_key != api_key:
        company.api_key = api_key

    customer = session.scalar(
        select(Customer).where(
            Customer.company_id == company.id,
            Customer.email == DEMO_CUSTOMER_EMAIL,
        )
    )
    if customer is None:
        customer = Customer(
            company_id=company.id,
            name=DEMO_CUSTOMER_NAME,
            email=DEMO_CUSTOMER_EMAIL,
        )
        session.add(customer)
    elif customer.name != DEMO_CUSTOMER_NAME:
        customer.name = DEMO_CUSTOMER_NAME

    session.commit()
    session.refresh(company)
    session.refresh(customer)
    return company, customer


def main() -> None:
    api_key = settings.demo_company_api_key.get_secret_value()
    if not api_key:
        raise RuntimeError(
            "DEMO_COMPANY_API_KEY is not set. Add it to your local .env before seeding."
        )

    with SessionLocal() as session:
        company, customer = seed_demo(session, api_key)

    print(
        f"Demo seed complete: company_id={company.id}, customer_id={customer.id}."
    )


if __name__ == "__main__":
    main()
