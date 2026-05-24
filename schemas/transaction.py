from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from typing import Any


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    payer_id: UUID
    receiver_id: UUID
    amount: Decimal = Field(..., description="Полная сумма заказа (hours × rate).")
    commission_amount: Decimal = Field(..., description="Комиссия платформы.")
    status: str
    created_at: datetime

    @computed_field(description="Сумма, начисленная исполнителю (amount − commission).")
    @property
    def worker_amount(self) -> Decimal:
        return self.amount - self.commission_amount


class TransactionListOut(BaseModel):
    items: list[TransactionOut]
    total: int
    limit: int
    offset: int
