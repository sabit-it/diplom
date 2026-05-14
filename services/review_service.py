import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.review import Review
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.order_repository import get_order_by_id
from repositories.review_repository import (
    create_review,
    get_review_by_order_and_author,
    list_reviews_for_author,
    list_reviews_for_order,
    list_reviews_for_recipient,
)
from schemas.review import ReviewCreate, ReviewOut
from utils.enums import OrderStatus, UserRole


def _refresh_worker_rating_from_reviews(db: Session, recipient_user_id: uuid.UUID) -> None:
    wp = db.execute(
        select(WorkerProfile).where(WorkerProfile.user_id == recipient_user_id)
    ).scalar_one_or_none()
    if wp is None:
        return
    row = db.execute(
        select(func.avg(Review.rating), func.count())
        .select_from(Review)
        .where(Review.recipient_id == recipient_user_id)
    ).one()
    avg_r, cnt = row[0], row[1] or 0
    n = int(cnt)
    wp.reviews_count = n
    if n and avg_r is not None:
        wp.rating_avg = Decimal(str(round(float(avg_r), 2))).quantize(Decimal("0.01"))
    else:
        wp.rating_avg = Decimal("0.00")
    db.add(wp)
    db.commit()
    db.refresh(wp)


def create_review_for_order(
    db: Session,
    author: User,
    payload: ReviewCreate,
) -> ReviewOut:
    order = get_order_by_id(db, payload.order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.status != OrderStatus.completed.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Отзыв можно оставить только по заказу в статусе completed",
        )

    if order.assigned_worker_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="У заказа нет назначенного исполнителя",
        )

    if author.id not in (order.employer_id, order.assigned_worker_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    recipient_id = (
        order.employer_id
        if author.id == order.assigned_worker_id
        else order.assigned_worker_id
    )

    if get_review_by_order_and_author(db, order.id, author.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Вы уже оставили отзыв по этому заказу",
        )

    normalized_text = (
        payload.text.strip()
        if payload.text and payload.text.strip()
        else None
    )

    rev = create_review(
        db,
        order_id=order.id,
        author_id=author.id,
        recipient_id=recipient_id,
        rating=payload.rating,
        text=normalized_text,
    )

    recipient = db.get(User, recipient_id)
    if recipient is not None and recipient.role == UserRole.worker.value:
        _refresh_worker_rating_from_reviews(db, recipient_id)

    return ReviewOut.model_validate(rev)


def list_my_received_reviews(db: Session, user: User) -> list[ReviewOut]:
    rows = list_reviews_for_recipient(db, user.id)
    return [ReviewOut.model_validate(r) for r in rows]


def list_my_given_reviews(db: Session, user: User) -> list[ReviewOut]:
    rows = list_reviews_for_author(db, user.id)
    return [ReviewOut.model_validate(r) for r in rows]


def list_order_reviews_for_participant(
    db: Session,
    user: User,
    order_id: uuid.UUID,
) -> list[ReviewOut]:
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if user.id not in (order.employer_id, order.assigned_worker_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    rows = list_reviews_for_order(db, order_id)
    return [ReviewOut.model_validate(r) for r in rows]
