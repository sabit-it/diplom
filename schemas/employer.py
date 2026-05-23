from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EmployerProfileUpsert(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "company_name": "ООО «Ремонт и Дело»",
                "address": "Москва, ул. Строителей, 10",
            },
        },
    )

    company_name: str | None = Field(
        default=None,
        max_length=255,
        description="Название компании или ИП; необязательно.",
    )
    address: str | None = Field(
        default=None,
        max_length=500,
        description="Юридический или фактический адрес; необязательно.",
    )


class EmployerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    company_name: str | None
    address: str | None
    created_at: datetime
    updated_at: datetime
