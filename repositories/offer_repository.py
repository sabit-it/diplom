import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.order_offer import OrderOffer
from utils.enums import OfferStatus


def create_offer(
    db: Session,
    *,
    order_id: uuid.UUID,
    worker_id: uuid.UUID,
    distance_meters: int,
    status: str = OfferStatus.sent.value,
) -> OrderOffer:
    offer = OrderOffer(
        order_id=order_id,
        worker_id=worker_id,
        distance_meters=distance_meters,
        status=status,
    )
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def get_offer_by_id(db: Session, offer_id: uuid.UUID) -> OrderOffer | None:
    return db.get(OrderOffer, offer_id)


def save_offer(db: Session, offer: OrderOffer) -> OrderOffer:
    db.add(offer)
    db.commit()
    db.refresh(offer)
    return offer


def worker_ids_with_offers_for_order(db: Session, order_id: uuid.UUID) -> set[uuid.UUID]:
    q = select(OrderOffer.worker_id).where(OrderOffer.order_id == order_id)
    rows = db.execute(q).scalars().all()
    return set(rows)


def list_pending_sent_offers_for_worker(db: Session, worker_id: uuid.UUID) -> list[OrderOffer]:
    q = (
        select(OrderOffer)
        .where(
            OrderOffer.worker_id == worker_id,
            OrderOffer.status == OfferStatus.sent.value,
        )
        .order_by(OrderOffer.sent_at.desc())
    )
    return list(db.execute(q).scalars().all())
