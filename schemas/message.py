from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class MessageCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"text": "Буду через 20 минут"}},
    )

    text: str = Field(..., min_length=1, max_length=5000, description="Текст сообщения.")


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор сообщения.")
    order_id: UUID = Field(..., description="Заказ, к которому относится сообщение.")
    sender_id: UUID = Field(..., description="Отправитель.")
    text: str = Field(..., description="Текст сообщения.")
    created_at: datetime = Field(..., description="Время отправки (UTC).")


class MessageListOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": (
                "Страница истории чата. Сообщения отсортированы от новых к старым. "
                "Если `next_cursor` не null — передайте его как `before` в следующем запросе."
            ),
        },
    )

    items: list[MessageOut] = Field(..., description="Сообщения на текущей странице (от новых к старым).")
    next_cursor: UUID | None = Field(
        None,
        description="ID самого старого сообщения в выборке. Передайте как `before` для загрузки следующей страницы. null — больше нет.",
    )
