from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from utils.enums import UserRole


class LoginRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"email": "user@example.com", "password": "secret12345"},
        },
    )

    email: str = Field(
        ...,
        description="Электронная почта (до нормализации можно передать с пробелами; будет приведена к нижнему регистру).",
    )
    password: str = Field(..., description="Пароль учётной записи.")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class RegisterRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "email": "worker@example.com",
                "password": "secret12345",
                "last_name": "Иванов",
                "first_name": "Иван",
                "patronymic": "Иванович",
                "role": "worker",
                "phone": "+79990001122",
                "photo_url": None,
            },
        },
    )

    email: EmailStr = Field(
        ...,
        min_length=3,
        max_length=255,
        description="Уникальный email; используется для входа.",
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Пароль не короче 8 символов; хранится в виде bcrypt(SHA256(UTF‑8)).",
    )
    last_name: str = Field(..., min_length=1, max_length=255, description="Фамилия.")
    first_name: str = Field(..., min_length=1, max_length=255, description="Имя.")
    patronymic: str | None = Field(
        default=None,
        max_length=255,
        description="Отчество; можно не указывать или передать пустую строку (будет сохранено как null).",
    )
    role: UserRole = Field(
        default=UserRole.worker,
        description=(
            "Роль в системе: **employer** — заказчик (создаёт заказы), **worker** — исполнитель "
            "(получает предложения по заказам). Значение влияет на доступные эндпоинты."
        ),
    )
    phone: str | None = Field(
        default=None,
        max_length=32,
        description="Телефон в международном формате; необязателен, но если указан — должен быть уникален.",
    )
    photo_url: str | None = Field(
        default=None,
        max_length=512,
        description="URL фотографии профиля (например CDN); необязательно.",
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("phone", mode="before")
    @classmethod
    def empty_phone_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v

    @field_validator("patronymic", mode="before")
    @classmethod
    def empty_patronymic_to_none(cls, v):
        if v == "" or v is None:
            return None
        return v


class TokenResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "expires_in": 3600,
            },
        },
    )

    access_token: str = Field(
        ...,
        description="JWT (HS256). В заголовке запросов: `Authorization: Bearer <access_token>`.",
    )
    token_type: str = Field(
        default="bearer",
        description="Тип токена для OAuth2; всегда `bearer`.",
    )
    expires_in: int = Field(
        ...,
        description="Время жизни access_token в секундах (из настроек `ACCESS_TOKEN_EXPIRE_MINUTES`).",
    )


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "first_name": "Иван",
                "last_name": "Иванов",
                "patronymic": "Иванович",
                "phone": "+79990001122",
                "photo_url": "https://cdn.example.com/photo.jpg",
            },
        },
    )

    first_name: str | None = Field(default=None, min_length=1, max_length=255, description="Имя.")
    last_name: str | None = Field(default=None, min_length=1, max_length=255, description="Фамилия.")
    patronymic: str | None = Field(default=None, max_length=255, description="Отчество; передайте пустую строку или null, чтобы очистить.")
    phone: str | None = Field(default=None, max_length=32, description="Телефон в международном формате; null — убрать номер.")
    photo_url: str | None = Field(default=None, max_length=512, description="URL фото профиля; null — убрать фото.")

    @field_validator("patronymic", mode="before")
    @classmethod
    def empty_patronymic_to_none(cls, v):
        if v == "":
            return None
        return v

    @field_validator("phone", mode="before")
    @classmethod
    def empty_phone_to_none(cls, v):
        if v == "":
            return None
        return v


class EmailChangeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"new_email": "new@example.com", "current_password": "secret12345"},
        },
    )

    new_email: EmailStr = Field(..., min_length=3, max_length=255, description="Новый email.")
    current_password: str = Field(..., description="Текущий пароль для подтверждения.")

    @field_validator("new_email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PasswordChangeRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {"current_password": "oldSecret1", "new_password": "newSecret2"},
        },
    )

    current_password: str = Field(..., description="Текущий пароль.")
    new_password: str = Field(..., min_length=8, max_length=128, description="Новый пароль (мин. 8 символов).")


class UserLocationUpdate(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"lat": "55.751244", "lng": "37.618423"}},
    )

    lat: Decimal = Field(
        ...,
        ge=Decimal("-90"),
        le=Decimal("90"),
        description="Широта WGS‑84, градусы; от −90 до 90.",
    )
    lng: Decimal = Field(
        ...,
        ge=Decimal("-180"),
        le=Decimal("180"),
        description="Долгота WGS‑84, градусы; от −180 до 180.",
    )


class UserPublic(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "description": "Публичные поля пользователя без пароля и служебных секретов.",
        },
    )

    id: UUID = Field(..., description="Идентификатор пользователя (UUID).")
    email: str = Field(..., description="Email.")
    phone: str | None = Field(None, description="Телефон или null.")
    last_name: str = Field(..., description="Фамилия.")
    first_name: str = Field(..., description="Имя.")
    patronymic: str | None = Field(None, description="Отчество или null.")
    role: UserRole = Field(..., description="Роль: employer или worker.")
    photo_url: str | None = Field(None, description="URL фото или null.")
    lat: Decimal | None = Field(
        None,
        description="Последняя известная широта пользователя (WGS‑84) или null.",
    )
    lng: Decimal | None = Field(
        None,
        description="Последняя известная долгота пользователя (WGS‑84) или null.",
    )
    location_updated_at: datetime | None = Field(
        None,
        description="Метка времени последнего обновления координат (UTC) или null.",
    )
    is_active: bool = Field(..., description="Активен ли аккаунт (заблокированные — false).")
    created_at: datetime = Field(..., description="Время создания записи.")
    updated_at: datetime = Field(..., description="Время последнего обновления записи.")
