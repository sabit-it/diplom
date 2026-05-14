from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from core.database import get_db
from repositories.profession_repository import get_profession_by_id, list_active_professions
from schemas.profession import ProfessionOut

router = APIRouter(prefix="/professions", tags=["Профессии"])


@router.get(
    "/",
    response_model=list[ProfessionOut],
    summary="Справочник профессий",
    description=(
        "Активные услуги с базовой ставкой и единицей расчёта (`rate_unit`). "
        "При создании заказа укажите соответствующий `profession_id`; сумма в заказе задаётся полями `hours` и "
        "`hourly_rate` на стороне клиента с учётом единицы (м², створки и т.д.)."
    ),
)
def list_professions(db: Session = Depends(get_db)) -> list[ProfessionOut]:
    rows = list_active_professions(db)
    return [ProfessionOut.model_validate(p) for p in rows]


@router.get(
    "/{profession_id}",
    response_model=ProfessionOut,
    summary="Профессия по id",
    description="Одна запись справочника по числовому идентификатору.",
)
def get_profession(
    profession_id: int,
    db: Session = Depends(get_db),
) -> ProfessionOut:
    p = get_profession_by_id(db, profession_id)
    if p is None or not p.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profession not found")
    return ProfessionOut.model_validate(p)
