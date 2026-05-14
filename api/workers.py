from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.worker import WorkerLinePatch, WorkerProfileOut, WorkerProfileUpsert
from services.worker_service import (
    get_my_worker_profile,
    set_worker_line_status,
    upsert_my_worker_profile,
)

router = APIRouter(prefix="/workers", tags=["Исполнители"])


@router.get(
    "/me/profile",
    response_model=WorkerProfileOut,
    summary="Мой профиль исполнителя",
    description="Только **worker**. Возвращает профиль с привязкой к профессии из справочника. Если профиля нет — 404.",
)
def read_my_worker_profile(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> WorkerProfileOut:
    return get_my_worker_profile(db, user)


@router.put(
    "/me/profile",
    response_model=WorkerProfileOut,
    summary="Создать или обновить профиль исполнителя",
    description=(
        "Только **worker**. `profession_id` должен существовать в `GET /professions/` и быть активным. "
        "Без профиля нельзя корректно выйти на линию и участвовать в диспетчеризации."
    ),
)
def put_my_worker_profile(
    payload: WorkerProfileUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> WorkerProfileOut:
    return upsert_my_worker_profile(db, user, payload)


@router.patch(
    "/me/line",
    response_model=WorkerProfileOut,
    summary="Выйти на линию / уйти с линии",
    description=(
        "**На линию** (`is_online: true`) — исполнитель участвует в подборе по гео; нужен профиль "
        "(`PUT /workers/me/profile`) и известные координаты (`PATCH /auth/me/location` или позже поля профиля). "
        "**С линии** (`is_online: false`) — заказы не предлагаются."
    ),
)
def patch_my_line_status(
    payload: WorkerLinePatch,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> WorkerProfileOut:
    return set_worker_line_status(db, user, payload)
