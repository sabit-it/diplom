from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from utils.enums import ProfessionRateUnit


class AdminUserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    phone: str | None
    last_name: str
    first_name: str
    patronymic: str | None
    role: str
    balance: Decimal
    is_active: bool
    is_blocked: bool
    is_admin: bool
    created_at: datetime


class AdminUserListOut(BaseModel):
    items: list[AdminUserOut]
    total: int
    limit: int
    offset: int


class AdminBlockRequest(BaseModel):
    is_blocked: bool = Field(..., description="true — заблокировать, false — разблокировать.")


class AdminOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    employer_id: UUID
    assigned_worker_id: UUID | None
    profession_id: int
    title: str
    status: str
    total_price: Decimal
    address: str
    created_at: datetime


class AdminOrderListOut(BaseModel):
    items: list[AdminOrderOut]
    total: int
    limit: int
    offset: int


class AdminTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    payer_id: UUID
    receiver_id: UUID
    order_id: UUID | None
    amount: Decimal
    commission_amount: Decimal
    type: str
    status: str
    created_at: datetime


class AdminTransactionListOut(BaseModel):
    items: list[AdminTransactionOut]
    total: int
    limit: int
    offset: int


class AdminStatsOut(BaseModel):
    total_users: int
    total_employers: int
    total_workers: int
    total_orders: int
    completed_orders: int
    cancelled_orders: int
    total_platform_revenue: Decimal = Field(..., description="Сумма комиссий платформы за все заказы.")
    total_volume: Decimal = Field(..., description="Общий оборот по всем транзакциям.")


class ProfessionCreate(BaseModel):
    id: int = Field(..., ge=1, le=32767, description="ID профессии (SmallInteger).")
    name: str = Field(..., min_length=1, max_length=100)
    hourly_rate: Decimal = Field(..., gt=0, max_digits=10, decimal_places=2)
    rate_unit: ProfessionRateUnit = Field(default=ProfessionRateUnit.hour)


class ProfessionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    hourly_rate: Decimal | None = Field(default=None, gt=0)
    rate_unit: ProfessionRateUnit | None = None
    is_active: bool | None = None
