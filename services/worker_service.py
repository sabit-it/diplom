from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.profession import Profession
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.profession_repository import require_active_profession
from repositories.worker_repository import (
    get_worker_profile_by_user_id,
    persist_worker_profile,
)
from schemas.profession import ProfessionOut
from schemas.worker import WorkerLinePatch, WorkerProfileOut, WorkerProfileUpsert
from utils.enums import UserRole


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
        )
        db.add(wp)
    else:
        wp.profession_id = payload.profession_id
        wp.about = about
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
