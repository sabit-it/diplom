from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"order_id": "00000000-0000-0000-0000-000000000001", "rating": 5, "text": "Всё отлично"},
        },
    )

    order_id: UUID = Field(
        ...,
        description="Заказ в статусе **completed**; автор определяется по JWT, оцениваемый — второй участник сделки.",
    )
    rating: int = Field(
        ...,
        ge=1,
        le=5,
        description="Оценка от 1 до 5 звёзд.",
    )
    text: str | None = Field(
        default=None,
        max_length=5000,
        description="Текст отзыва; необязательно.",
    )


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор отзыва.")
    order_id: UUID = Field(..., description="Связанный заказ.")
    author_id: UUID = Field(..., description="Кто оставил отзыв.")
    recipient_id: UUID = Field(..., description="Кого оценили.")
    rating: int = Field(..., description="Оценка 1–5.")
    text: str | None = Field(None, description="Текст или null.")
    created_at: datetime = Field(..., description="Время создания.")
