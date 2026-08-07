from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_company
from app.db.session import get_db
from app.models import Company, Customer, Order
from app.schemas.orders import OrderCreate, OrderResponse


router = APIRouter()


def _get_tenant_customer(
    db: Session, company_id: int, customer_id: int
) -> Customer:
    customer = db.scalar(
        select(Customer).where(
            Customer.id == customer_id,
            Customer.company_id == company_id,
        )
    )
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> Order:
    _get_tenant_customer(db, current_company.id, payload.customer_id)

    order = Order(
        company_id=current_company.id,
        customer_id=payload.customer_id,
        external_order_id=payload.external_order_id,
        product_name=payload.product_name,
        amount=payload.amount,
        status=payload.status,
    )
    db.add(order)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An order with this external_order_id already exists",
        ) from exc
    db.refresh(order)
    return order


@router.get("/orders/{order_id}", response_model=OrderResponse)
def get_order(
    order_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> Order:
    order = db.scalar(
        select(Order).where(
            Order.id == order_id,
            Order.company_id == current_company.id,
        )
    )
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")
    return order


@router.get("/customers/{customer_id}/orders", response_model=list[OrderResponse])
def get_customer_orders(
    customer_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_company: Annotated[Company, Depends(get_current_company)],
) -> list[Order]:
    _get_tenant_customer(db, current_company.id, customer_id)
    return list(
        db.scalars(
            select(Order)
            .where(
                Order.company_id == current_company.id,
                Order.customer_id == customer_id,
            )
            .order_by(Order.created_at, Order.id)
        ).all()
    )
