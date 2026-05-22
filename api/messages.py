from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.message import MessageCreate, MessageListOut, MessageOut
from services.chat_service import list_messages, send_message

router = APIRouter(prefix="/messages", tags=["Сообщения"])


@router.post(
    "/{order_id}",
    response_model=MessageOut,
    status_code=status.HTTP_201_CREATED,
    summary="Отправить сообщение",
    description=(
        "Доступно только **участникам заказа** (заказчику или назначенному исполнителю) "
        "пока заказ в статусе **assigned**. "
        "На других статусах (pending_offer, completed, cancelled) вернётся 409."
    ),
)
def post_message(
    order_id: UUID,
    payload: MessageCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> MessageOut:
    return send_message(db, user, order_id, payload)


@router.get(
    "/{order_id}",
    response_model=MessageListOut,
    summary="История чата",
    description=(
        "Возвращает сообщения по заказу от новых к старым. "
        "Доступно только участникам заказа в статусе **assigned**. "
        "Для постраничной загрузки передайте `before` = `next_cursor` из предыдущего ответа. "
        "`limit` по умолчанию 50, максимум 100."
    ),
)
def get_messages(
    order_id: UUID,
    before: UUID | None = Query(default=None, description="Курсор: id сообщения — вернуть только более старые."),
    limit: int = Query(default=50, ge=1, le=100, description="Количество сообщений на странице."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> MessageListOut:
    return list_messages(db, user, order_id, before_id=before, limit=limit)
