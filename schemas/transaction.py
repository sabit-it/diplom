from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator


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


class WithdrawRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "amount": "500.00",
                "card_number": "4111111111111111",
                "card_holder": "IVAN IVANOV",
                "expiry_month": 12,
                "expiry_year": 2027,
                "cvv": "123",
            }
        }
    )

    amount: Decimal = Field(
        ...,
        gt=0,
        le=Decimal("1000000"),
        max_digits=12,
        decimal_places=2,
        description="Сумма вывода в рублях. Минимум 0.01, максимум 1 000 000.",
    )
    card_number: str = Field(..., pattern=r"^\d{16,19}$", description="Номер карты, только цифры.")
    card_holder: str = Field(..., min_length=2, max_length=100, description="Имя держателя карты латиницей.")
    expiry_month: int = Field(..., ge=1, le=12, description="Месяц истечения карты (1–12).")
    expiry_year: int = Field(..., ge=2024, le=2040, description="Год истечения карты.")
    cvv: str = Field(..., pattern=r"^\d{3,4}$", description="CVV/CVC код.")

    @model_validator(mode="after")
    def check_not_expired(self) -> "WithdrawRequest":
        today = date.today()
        if (self.expiry_year, self.expiry_month) < (today.year, today.month):
            raise ValueError("Срок действия карты истёк.")
        return self


class WithdrawOut(BaseModel):
    transaction_id: UUID = Field(..., description="Идентификатор созданной транзакции.")
    amount: Decimal = Field(..., description="Выведенная сумма.")
    new_balance: Decimal = Field(..., description="Баланс после вывода.")
    card_last4: str = Field(..., description="Последние 4 цифры карты.")


class TransactionSummaryOut(BaseModel):
    current_balance: Decimal = Field(..., description="Текущий баланс.")
    total_deposited: Decimal = Field(..., description="Всего пополнено (deposit).")
    total_withdrawn: Decimal = Field(..., description="Всего выведено (withdrawal).")
    total_earned: Decimal = Field(..., description="Всего заработано на заказах (worker).")
    total_spent: Decimal = Field(..., description="Всего потрачено на заказы (employer).")
