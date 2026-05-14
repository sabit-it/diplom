from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from utils.enums import ProfessionRateUnit


class ProfessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Идентификатор профессии (совпадает с `profession_id` в заказе и профиле).")
    name: str = Field(..., description="Название услуги.")
    hourly_rate: Decimal = Field(
        ...,
        description=(
            "Базовая ставка (число из прайса): при `rate_unit=hour` — руб/час; "
            "`square_meter` — руб/м²; `window_sash` — руб/створка."
        ),
    )
    rate_unit: ProfessionRateUnit = Field(
        ...,
        description="Единица расчёта: **hour** — почасовая, **square_meter** — за м², **window_sash** — за створку окна.",
    )
    is_active: bool = Field(..., description="Доступна ли профессия для новых заказов.")
