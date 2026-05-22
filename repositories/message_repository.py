import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.message import Message


def create_message(db: Session, *, order_id: uuid.UUID, sender_id: uuid.UUID, text: str) -> Message:
    msg = Message(order_id=order_id, sender_id=sender_id, text=text)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_messages_page(
    db: Session,
    order_id: uuid.UUID,
    *,
    before_id: uuid.UUID | None,
    limit: int,
) -> list[Message]:
    q = select(Message).where(Message.order_id == order_id)

    if before_id is not None:
        # Курсор: берём только сообщения старше указанного (по created_at).
        # Подзапрос нужен, чтобы не хранить created_at на клиенте — достаточно id.
        anchor = db.get(Message, before_id)
        if anchor is not None:
            q = q.where(Message.created_at < anchor.created_at)

    q = q.order_by(Message.created_at.desc()).limit(limit)
    return list(db.execute(q).scalars().all())
