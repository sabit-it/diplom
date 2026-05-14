from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field

from utils.enums import OfferStatus, OrderStatus, UserRole


class OrderCreate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "profession_id": 1,
                "title": "Уборка квартиры",
                "description": "2 комнаты, без химии",
                "hours": 4,
                "hourly_rate": "500.00",
                "address": "Москва, ул. Примерная, 1",
                "lat": "55.751244",
                "lng": "37.618423",
                "scheduled_at": None,
            },
        },
    )

    profession_id: int = Field(
        ...,
        ge=1,
        description="Идентификатор профессии из справочника `GET /professions/`; должен совпадать с профессией исполнителей, которым уйдёт предложение.",
    )
    title: str = Field(..., min_length=1, max_length=255, description="Краткое название заказа.")
    description: str | None = Field(
        default=None,
        max_length=5000,
        description="Подробное описание работ; можно не передавать.",
    )
    hours: int = Field(
        ...,
        ge=1,
        le=168,
        description="Планируемая длительность работ в часах (от 1 до 168).",
    )
    hourly_rate: Decimal = Field(
        ...,
        gt=0,
        max_digits=10,
        decimal_places=2,
        description="Ставка за час в денежных единицах; вместе с `hours` задаёт расчёт `total_price`.",
    )
    address: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Полный адрес или ориентир места выполнения работ (для исполнителя).",
    )
    lat: Decimal = Field(
        ...,
        ge=Decimal("-90"),
        le=Decimal("90"),
        description="Широта точки работ WGS‑84; используется для поиска ближайшего исполнителя.",
    )
    lng: Decimal = Field(
        ...,
        ge=Decimal("-180"),
        le=Decimal("180"),
        description="Долгота точки работ WGS‑84.",
    )
    scheduled_at: datetime | None = Field(
        default=None,
        description="Желаемое время начала работ (UTC или с таймзоной); необязательно.",
    )

    @computed_field
    @property
    def total_price(self) -> Decimal:
        return (Decimal(self.hours) * self.hourly_rate).quantize(Decimal("0.01"))


class OrderSummary(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Сводка по заказу: цена, адрес, гео, статус диспетчеризации.",
        },
    )

    id: UUID = Field(..., description="Идентификатор заказа.")
    employer_id: UUID = Field(..., description="Заказчик (владелец заказа).")
    profession_id: int = Field(..., description="Профессия, по которой подбираются исполнители.")
    title: str = Field(..., description="Название.")
    description: str | None = Field(None, description="Описание или null.")
    hours: int = Field(..., description="Часы.")
    hourly_rate: Decimal = Field(..., description="Ставка за час.")
    total_price: Decimal = Field(..., description="Итоговая сумма (hours × hourly_rate).")
    address: str = Field(..., description="Адрес / ориентир.")
    lat: Decimal = Field(..., description="Широта места работ.")
    lng: Decimal = Field(..., description="Долгота места работ.")
    scheduled_at: datetime | None = Field(None, description="Запланированное время или null.")
    status: OrderStatus = Field(
        ...,
        description=(
            "`pending_offer` — ждём ответ исполнителя по текущему предложению; "
            "`assigned` — исполнитель принял заказ; "
            "`completed` — работы завершены, можно оставлять отзывы; "
            "`cancelled` — отменён; "
            "`no_workers_available` — нет подходящих исполнителей или все отказались."
        ),
    )
    assigned_worker_id: UUID | None = Field(
        None,
        description="Исполнитель после принятия; до принятия — null.",
    )
    created_at: datetime = Field(..., description="Создание записи.")
    updated_at: datetime = Field(..., description="Последнее обновление записи.")


class WorkerLocationOut(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"lat": "55.75", "lng": "37.61", "source": "worker_profile"},
        },
    )

    lat: Decimal | None = Field(None, description="Широта или null, если координат нет.")
    lng: Decimal | None = Field(None, description="Долгота или null.")
    source: str = Field(
        ...,
        description=(
            "Источник координат: **worker_profile** — поля `current_lat`/`current_lng` профиля исполнителя; "
            "**user** — последние `lat`/`lng` пользователя."
        ),
    )


class AssignedWorkerOut(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Публичные данные принятого исполнителя и его актуальная геопозиция (если есть).",
        },
    )

    id: UUID = Field(..., description="Идентификатор пользователя‑исполнителя.")
    email: str = Field(..., description="Email исполнителя.")
    phone: str | None = Field(None, description="Телефон.")
    last_name: str = Field(..., description="Фамилия.")
    first_name: str = Field(..., description="Имя.")
    patronymic: str | None = Field(None, description="Отчество.")
    role: UserRole = Field(..., description="Роль (ожидается worker).")
    photo_url: str | None = Field(None, description="Фото.")
    rating_avg: Decimal = Field(..., description="Средний рейтинг из профиля исполнителя.")
    reviews_count: int = Field(..., description="Количество отзывов.")
    completed_orders: int = Field(..., description="Число завершённых заказов (из профиля).")
    location: WorkerLocationOut = Field(..., description="Координаты и источник.")


class OrderParticipantView(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "Карточка заказа для заказчика или назначенного исполнителя.",
        },
    )

    order: OrderSummary = Field(..., description="Данные заказа.")
    assigned_worker: AssignedWorkerOut | None = Field(
        None,
        description="Заполняется после принятия заказа исполнителем; иначе null.",
    )


class OrderAcceptedNotification(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "Ответ API после **принятия** заказа: место работ, суммы и полный профиль исполнителя с гео.",
        },
    )

    order: OrderSummary = Field(
        ...,
        description="Заказ в статусе `assigned`; поля `lat`/`lng`/`address` — где выполнять работу.",
    )
    worker: AssignedWorkerOut = Field(
        ...,
        description="Исполнитель, который принял предложение; `location` — для навигатора к нему.",
    )


class OrderCreateResult(BaseModel):
    order: OrderSummary = Field(..., description="Созданный заказ.")
    active_offer_id: UUID | None = Field(
        None,
        description="Идентификатор первого предложения (`order_offers`), если исполнитель найден; иначе null.",
    )
    message: str | None = Field(
        None,
        description="Пояснение, если исполнитель сразу не найден (например нет онлайн с координатами).",
    )


class OfferSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Идентификатор предложения.")
    order_id: UUID = Field(..., description="Связанный заказ.")
    worker_id: UUID = Field(..., description="Исполнитель, которому отправлено предложение.")
    distance_meters: int = Field(
        ...,
        description="Расстояние от исполнителя до точки заказа на момент отправки (метры, гаверсинус).",
    )
    status: OfferStatus = Field(
        ...,
        description="`sent` — ожидается ответ; `accepted` / `declined` — после ответа исполнителя.",
    )
    sent_at: datetime = Field(..., description="Когда предложение создано.")
    responded_at: datetime | None = Field(None, description="Когда исполнитель ответил или null.")


class PendingOfferForWorker(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "Элемент списка входящих предложений для исполнителя.",
        },
    )

    offer: OfferSummary = Field(..., description="Предложение со статусом `sent`.")
    order: OrderSummary = Field(..., description="Заказ в статусе `pending_offer`.")


class OfferRespondRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"accept": True}},
    )

    accept: bool = Field(
        ...,
        description="**true** — принять заказ (назначение исполнителем); **false** — отказ (предложение следующему).",
    )


class OfferDeclinedResult(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "description": "Результат отказа от предложения: обновлённый заказ и, при наличии, id следующего предложения.",
        },
    )

    declined: bool = Field(default=True, description="Всегда true для этого типа ответа.")
    order: OrderSummary = Field(..., description="Текущее состояние заказа.")
    next_offer_id: UUID | None = Field(
        None,
        description="Если найден следующий исполнитель — id нового предложения; иначе null и статус заказа может стать `no_workers_available`.",
    )
    message: str | None = Field(None, description="Краткое пояснение для клиента.")
