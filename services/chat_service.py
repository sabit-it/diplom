import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.user import User
from repositories.message_repository import create_message, get_messages_page
from repositories.order_repository import get_order_by_id
from schemas.message import MessageCreate, MessageListOut, MessageOut
from utils.enums import OrderStatus

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 50


def _check_chat_access(db: Session, user: User, order_id: uuid.UUID):
    """Возвращает заказ, если пользователь — участник и заказ в assigned."""
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    is_participant = order.employer_id == user.id or order.assigned_worker_id == user.id
    if not is_participant:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if order.status != OrderStatus.assigned.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Чат доступен только для заказов в статусе assigned",
        )
    return order


def send_message(
    db: Session,
    user: User,
    order_id: uuid.UUID,
    payload: MessageCreate,
) -> MessageOut:
    _check_chat_access(db, user, order_id)
    msg = create_message(db, order_id=order_id, sender_id=user.id, text=payload.text.strip())
    return MessageOut.model_validate(msg)


def list_messages(
    db: Session,
    user: User,
    order_id: uuid.UUID,
    *,
    before_id: uuid.UUID | None,
    limit: int,
) -> MessageListOut:
    _check_chat_access(db, user, order_id)

    # Ограничиваем лимит, чтобы клиент не запросил всю историю разом.
    limit = min(limit, _MAX_LIMIT)

    messages = get_messages_page(db, order_id, before_id=before_id, limit=limit)
    items = [MessageOut.model_validate(m) for m in messages]

    # Если вернулось ровно limit — возможно, есть ещё; даём курсор.
    next_cursor = items[-1].id if len(items) == limit else None

    return MessageListOut(items=items, next_cursor=next_cursor)
