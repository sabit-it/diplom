from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from schemas.profession import ProfessionOut


class WorkerProfileUpsert(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"profession_id": 3, "about": "Сборка кухонь и шкафов, свой инструмент"},
        },
    )

    profession_id: int = Field(
        ...,
        ge=1,
        description="Идентификатор профессии из `GET /professions/` (только активные).",
    )
    about: str | None = Field(
        default=None,
        max_length=5000,
        description="Кратко о себе; необязательно.",
    )
    max_distance_km: int | None = Field(
        default=None,
        ge=1,
        le=500,
        description="Максимальное расстояние до заказа (км). Dispatch не предложит заказ дальше этого радиуса. null — без ограничений.",
    )


class WorkerLinePatch(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"is_online": True}})

    is_online: bool = Field(
        ...,
        description="true — на линии (готов принимать заказы), false — не ищу работу сейчас.",
    )


class WorkerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    profession: ProfessionOut
    about: str | None
    max_distance_km: int | None
    rating_avg: Decimal
    reviews_count: int
    completed_orders: int
    is_online: bool
    current_lat: Decimal | None
    current_lng: Decimal | None
    last_location_at: datetime | None
