from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID | None
    payer_id: UUID
    receiver_id: UUID
    amount: Decimal = Field(..., description="Сумма операции.")
    commission_amount: Decimal = Field(..., description="Комиссия платформы (0 для депозитов).")
    type: str = Field(..., description="Тип: order_settlement — расчёт по заказу, deposit — пополнение баланса.")
    status: str
    created_at: datetime

    @computed_field(description="Сумма за вычетом комиссии.")
    @property
    def worker_amount(self) -> Decimal:
        return self.amount - self.commission_amount


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int


class DepositRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"amount": "1000.00"}},
    )

    amount: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("1000000"),
        max_digits=12,
        decimal_places=2,
        description="Сумма пополнения в рублях. Минимум 0.01, максимум 1 000 000.",
    )


class DepositOut(BaseModel):
    transaction_id: UUID = Field(..., description="Идентификатор созданной транзакции.")
    amount: Decimal = Field(..., description="Зачисленная сумма.")
    new_balance: Decimal = Field(..., description="Баланс после пополнения.")
