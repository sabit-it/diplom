from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.profession import Profession
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.profession_repository import require_active_profession
from repositories.worker_repository import (
    get_worker_profile_by_user_id,
    list_all_workers_for_geo,
    list_workers_catalog,
    persist_worker_profile,
)
from utils.geo import haversine_meters
from schemas.profession import ProfessionOut
from schemas.worker import (
    WorkerCatalogItem,
    WorkerCatalogOut,
    WorkerLinePatch,
    WorkerProfileOut,
    WorkerProfileUpsert,
)
from utils.enums import UserRole


def _resolve_worker_coords(user: User, profile: WorkerProfile) -> tuple[Decimal, Decimal] | None:
    if profile.current_lat is not None and profile.current_lng is not None:
        return profile.current_lat, profile.current_lng
    if user.lat is not None and user.lng is not None:
        return user.lat, user.lng
    return None


def _build_catalog_item(
    db: Session,
    user: User,
    profile: WorkerProfile,
    distance_meters: int | None = None,
) -> WorkerCatalogItem | None:
    prof = db.get(Profession, profile.profession_id)
    if prof is None:
        return None
    return WorkerCatalogItem(
        id=profile.id,
        user_id=profile.user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        photo_url=user.photo_url,
        profession=ProfessionOut.model_validate(prof),
        about=profile.about,
        max_distance_km=profile.max_distance_km,
        rating_avg=profile.rating_avg,
        reviews_count=profile.reviews_count,
        completed_orders=profile.completed_orders,
        is_online=profile.is_online,
        distance_meters=distance_meters,
    )


def list_workers(
    db: Session,
    *,
    profession_id: int | None,
    min_rating: Decimal | None,
    is_online: bool | None,
    limit: int,
    offset: int,
    lat: Decimal | None = None,
    lng: Decimal | None = None,
    max_distance_km: int | None = None,
) -> WorkerCatalogOut:
    if lat is not None and lng is not None:
        return _list_workers_by_geo(
            db,
            profession_id=profession_id,
            min_rating=min_rating,
            is_online=is_online,
            limit=limit,
            offset=offset,
            lat=lat,
            lng=lng,
            max_distance_km=max_distance_km,
        )

    rows, total = list_workers_catalog(
        db,
        profession_id=profession_id,
        min_rating=min_rating,
        is_online=is_online,
        limit=limit,
        offset=offset,
    )
    items: list[WorkerCatalogItem] = []
    for user, profile in rows:
        item = _build_catalog_item(db, user, profile)
        if item is not None:
            items.append(item)
    return WorkerCatalogOut(items=items, total=total, limit=limit, offset=offset)


def _list_workers_by_geo(
    db: Session,
    *,
    profession_id: int | None,
    min_rating: Decimal | None,
    is_online: bool | None,
    limit: int,
    offset: int,
    lat: Decimal,
    lng: Decimal,
    max_distance_km: int | None,
) -> WorkerCatalogOut:
    all_rows = list_all_workers_for_geo(
        db,
        profession_id=profession_id,
        min_rating=min_rating,
        is_online=is_online,
    )

    # Вычисляем расстояние для каждого и фильтруем тех, у кого нет координат.
    with_dist: list[tuple[User, WorkerProfile, int]] = []
    for user, profile in all_rows:
        coords = _resolve_worker_coords(user, profile)
        if coords is None:
            continue
        dist_m = int(haversine_meters(lat, lng, coords[0], coords[1]))
        if max_distance_km is not None and dist_m > max_distance_km * 1000:
            continue
        with_dist.append((user, profile, dist_m))

    # Сортируем: ближайшие первыми.
    with_dist.sort(key=lambda x: x[2])

    total = len(with_dist)
    page = with_dist[offset: offset + limit]

    items: list[WorkerCatalogItem] = []
    for user, profile, dist_m in page:
        item = _build_catalog_item(db, user, profile, distance_meters=dist_m)
        if item is not None:
            items.append(item)
    return WorkerCatalogOut(items=items, total=total, limit=limit, offset=offset)


def _has_location_for_dispatch(user: User, profile: WorkerProfile | None) -> bool:
    if profile is not None and profile.current_lat is not None and profile.current_lng is not None:
        return True
    return user.lat is not None and user.lng is not None


def _to_profile_out(db: Session, profile: WorkerProfile) -> WorkerProfileOut:
    prof = db.get(Profession, profile.profession_id)
    if prof is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Profession missing for worker profile",
        )
    return WorkerProfileOut(
        id=profile.id,
        user_id=profile.user_id,
        profession=ProfessionOut.model_validate(prof),
        about=profile.about,
        max_distance_km=profile.max_distance_km,
        rating_avg=profile.rating_avg,
        reviews_count=profile.reviews_count,
        completed_orders=profile.completed_orders,
        is_online=profile.is_online,
        current_lat=profile.current_lat,
        current_lng=profile.current_lng,
        last_location_at=profile.last_location_at,
    )


def get_my_worker_profile(db: Session, user: User) -> WorkerProfileOut:
    if user.role != UserRole.worker.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workers only")
    wp = get_worker_profile_by_user_id(db, user.id)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль исполнителя не создан. Используйте PUT /workers/me/profile",
        )
    return _to_profile_out(db, wp)


def upsert_my_worker_profile(
    db: Session,
    user: User,
    payload: WorkerProfileUpsert,
) -> WorkerProfileOut:
    if user.role != UserRole.worker.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workers only")

    require_active_profession(db, payload.profession_id)

    about = (
        payload.about.strip()
        if payload.about and payload.about.strip()
        else None
    )

    wp = get_worker_profile_by_user_id(db, user.id)
    if wp is None:
        wp = WorkerProfile(
            user_id=user.id,
            profession_id=payload.profession_id,
            about=about,
            max_distance_km=payload.max_distance_km,
        )
        db.add(wp)
    else:
        wp.profession_id = payload.profession_id
        wp.about = about
        wp.max_distance_km = payload.max_distance_km
    persist_worker_profile(db, wp)
    return _to_profile_out(db, wp)


def set_worker_line_status(
    db: Session,
    user: User,
    payload: WorkerLinePatch,
) -> WorkerProfileOut:
    if user.role != UserRole.worker.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Workers only")

    wp = get_worker_profile_by_user_id(db, user.id)
    if wp is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Сначала создайте профиль исполнителя: PUT /workers/me/profile",
        )

    require_active_profession(db, wp.profession_id)

    if payload.is_online and not _has_location_for_dispatch(user, wp):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Чтобы выйти на линию, нужны координаты: обновите PUT /auth/me/location "
                "или координаты в профиле исполнителя (будущее расширение)."
            ),
        )

    wp.is_online = payload.is_online
    persist_worker_profile(db, wp)
    return _to_profile_out(db, wp)
