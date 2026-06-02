from decimal import Decimal

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user
from models.user import User
from schemas.worker import WorkerCatalogItem, WorkerCatalogOut, WorkerLinePatch, WorkerProfileOut, WorkerProfileUpsert
from services.worker_service import (
    get_my_worker_profile,
    get_public_worker_profile,
    list_workers,
    set_worker_line_status,
    upsert_my_worker_profile,
)

router = APIRouter(prefix="/workers", tags=["Исполнители"])


@router.get(
    "/",
    response_model=WorkerCatalogOut,
    summary="Каталог исполнителей",
    description=(
        "Возвращает список исполнителей с профилями. Доступен всем авторизованным пользователям. "
        "**Режим без геопозиции** (по умолчанию): сортировка по рейтингу. "
        "**Режим с геопозицией** (`lat` + `lng` обязательны вместе): сортировка по расстоянию (ближайшие первыми), "
        "в ответе появляется поле `distance_meters`. Исполнители без известных координат не попадают в выдачу. "
        "Дополнительный фильтр `max_distance_km` оставляет только тех, кто ближе указанного радиуса. "
        "Остальные фильтры: `profession_id`, `min_rating`, `is_online`. Пагинация: `limit` (макс. 100) + `offset`."
    ),
)
def get_workers_catalog(
    profession_id: int | None = Query(default=None, description="Фильтр по профессии."),
    min_rating: float | None = Query(default=None, ge=0, le=5, description="Минимальный рейтинг (0–5)."),
    is_online: bool | None = Query(default=None, description="true — только онлайн, false — только офлайн."),
    lat: float | None = Query(default=None, ge=-90, le=90, description="Широта точки поиска (WGS-84). Передавать вместе с lng."),
    lng: float | None = Query(default=None, ge=-180, le=180, description="Долгота точки поиска (WGS-84). Передавать вместе с lat."),
    max_distance_km: int | None = Query(default=None, ge=1, le=500, description="Максимальный радиус поиска (км). Работает только при указанных lat+lng."),
    limit: int = Query(default=20, ge=1, le=100, description="Кол-во записей на странице."),
    offset: int = Query(default=0, ge=0, description="Смещение от начала списка."),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> WorkerCatalogOut:
    if (lat is None) != (lng is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Параметры lat и lng должны передаваться вместе.",
        )
    min_rating_dec = Decimal(str(min_rating)) if min_rating is not None else None
    lat_dec = Decimal(str(lat)) if lat is not None else None
    lng_dec = Decimal(str(lng)) if lng is not None else None
    return list_workers(
        db,
        profession_id=profession_id,
        min_rating=min_rating_dec,
        is_online=is_online,
        limit=limit,
        offset=offset,
        lat=lat_dec,
        lng=lng_dec,
        max_distance_km=max_distance_km,
    )


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


@router.get(
    "/{user_id}",
    response_model=WorkerCatalogItem,
    summary="Профиль исполнителя по user_id",
)
def get_worker_by_user_id(
    user_id: uuid.UUID,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_active_user),
) -> WorkerCatalogItem:
    return get_public_worker_profile(db, user_id)
