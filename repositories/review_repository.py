import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.review import Review


def get_review_by_order_and_author(
    db: Session,
    order_id: uuid.UUID,
    author_id: uuid.UUID,
) -> Review | None:
    q = select(Review).where(
        Review.order_id == order_id,
        Review.author_id == author_id,
    )
    return db.execute(q).scalar_one_or_none()


def create_review(
    db: Session,
    *,
    order_id: uuid.UUID,
    author_id: uuid.UUID,
    recipient_id: uuid.UUID,
    rating: int,
    text: str | None,
) -> Review:
    rev = Review(
        order_id=order_id,
        author_id=author_id,
        recipient_id=recipient_id,
        rating=rating,
        text=text,
    )
    db.add(rev)
    db.commit()
    db.refresh(rev)
    return rev


def list_reviews_for_recipient(db: Session, recipient_id: uuid.UUID) -> list[Review]:
    q = (
        select(Review)
        .where(Review.recipient_id == recipient_id)
        .order_by(Review.created_at.desc())
    )
    return list(db.execute(q).scalars().all())


def list_reviews_for_author(db: Session, author_id: uuid.UUID) -> list[Review]:
    q = (
        select(Review)
        .where(Review.author_id == author_id)
        .order_by(Review.created_at.desc())
    )
    return list(db.execute(q).scalars().all())


def list_reviews_for_order(db: Session, order_id: uuid.UUID) -> list[Review]:
    q = select(Review).where(Review.order_id == order_id).order_by(Review.created_at.asc())
    return list(db.execute(q).scalars().all())
