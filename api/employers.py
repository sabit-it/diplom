from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.employer import EmployerProfileOut, EmployerProfileUpsert
from services.employer_service import get_my_employer_profile, upsert_my_employer_profile

router = APIRouter(prefix="/employers", tags=["Заказчики"])


@router.get(
    "/me",
    response_model=EmployerProfileOut,
    summary="Мой профиль заказчика",
    description=(
        "Только **employer**. Возвращает профиль компании (`company_name`, `address`). "
        "Если профиль ещё не создан — 404."
    ),
)
def read_my_employer_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> EmployerProfileOut:
    return get_my_employer_profile(db, user)


@router.put(
    "/me",
    response_model=EmployerProfileOut,
    summary="Создать или обновить профиль заказчика",
    description=(
        "Только **employer**. Оба поля необязательны: "
        "`company_name` — название компании/ИП, `address` — адрес. "
        "Передайте `null` или пустую строку, чтобы очистить поле."
    ),
)
def put_my_employer_profile(
    payload: EmployerProfileUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> EmployerProfileOut:
    return upsert_my_employer_profile(db, user, payload)
