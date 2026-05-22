import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.order import Order
from utils.enums import OrderStatus


def create_order(
    db: Session,
    *,
    employer_id: uuid.UUID,
    profession_id: int,
    title: str,
    description: str | None,
    hours: int,
    hourly_rate: Decimal,
    total_price: Decimal,
    address: str,
    lat: Decimal,
    lng: Decimal,
    scheduled_at: datetime | None,
    status: str,
) -> Order:
    order = Order(
        employer_id=employer_id,
        profession_id=profession_id,
        title=title,
        description=description,
        hours=hours,
        hourly_rate=hourly_rate,
        total_price=total_price,
        address=address,
        lat=lat,
        lng=lng,
        scheduled_at=scheduled_at,
        status=status,
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def get_order_by_id(db: Session, order_id: uuid.UUID) -> Order | None:
    return db.get(Order, order_id)


def save_order(db: Session, order: Order) -> Order:
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def list_orders_for_employer(
    db: Session,
    employer_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[Order]:
    q = select(Order).where(Order.employer_id == employer_id)
    if status is not None:
        q = q.where(Order.status == status)
    q = q.order_by(Order.created_at.desc())
    return list(db.execute(q).scalars().all())


def list_orders_for_worker(
    db: Session,
    worker_id: uuid.UUID,
    *,
    status: str | None = None,
) -> list[Order]:
    q = select(Order).where(Order.assigned_worker_id == worker_id)
    if status is not None:
        q = q.where(Order.status == status)
    q = q.order_by(Order.created_at.desc())
    return list(db.execute(q).scalars().all())
