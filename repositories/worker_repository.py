import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.order import Order
from models.order_offer import OrderOffer
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.profession_repository import require_active_profession
from utils.enums import OfferStatus, OrderStatus, UserRole
from utils.geo import haversine_meters


def get_busy_worker_ids(db: Session) -> set[uuid.UUID]:
    """
    Возвращает id воркеров, которые сейчас недоступны для новых заказов:
    - уже назначены на заказ (assigned)
    - имеют ожидающий ответа оффер (sent) по любому заказу
    """
    assigned_ids = set(
        db.execute(
            select(Order.assigned_worker_id).where(
                Order.status == OrderStatus.assigned.value,
                Order.assigned_worker_id.is_not(None),
            )
        ).scalars()
    )
    pending_offer_ids = set(
        db.execute(
            select(OrderOffer.worker_id).where(
                OrderOffer.status == OfferStatus.sent.value,
            )
        ).scalars()
    )
    return assigned_ids | pending_offer_ids


def _worker_coords(
    user: User,
    profile: WorkerProfile,
) -> tuple[Decimal, Decimal] | None:
    if profile.current_lat is not None and profile.current_lng is not None:
        return profile.current_lat, profile.current_lng
    if user.lat is not None and user.lng is not None:
        return user.lat, user.lng
    return None


def find_nearest_available_worker(
    db: Session,
    *,
    profession_id: int,
    order_lat: Decimal,
    order_lng: Decimal,
    exclude_worker_ids: set[uuid.UUID],
) -> tuple[User, WorkerProfile, float] | None:
    require_active_profession(db, profession_id)

    # Исключаем воркеров занятых любым другим заказом или оффером
    busy_ids = get_busy_worker_ids(db)
    skip = exclude_worker_ids | busy_ids

    q = (
        select(User, WorkerProfile)
        .join(WorkerProfile, WorkerProfile.user_id == User.id)
        .where(
            User.role == UserRole.worker.value,
            WorkerProfile.profession_id == profession_id,
            WorkerProfile.is_online.is_(True),
        )
    )
    candidates: list[tuple[User, WorkerProfile, float]] = []
    for user, profile in db.execute(q).all():
        if user.id in skip:
            continue
        coords = _worker_coords(user, profile)
        if coords is None:
            continue
        wlat, wlng = coords
        dist = haversine_meters(order_lat, order_lng, wlat, wlng)
        candidates.append((user, profile, dist))

    if not candidates:
        return None
    candidates.sort(key=lambda x: x[2])
    user, profile, dist = candidates[0]
    return user, profile, dist


def get_worker_profile_by_user_id(db: Session, user_id: uuid.UUID) -> WorkerProfile | None:
    q = select(WorkerProfile).where(WorkerProfile.user_id == user_id)
    return db.execute(q).scalar_one_or_none()


def persist_worker_profile(db: Session, profile: WorkerProfile) -> WorkerProfile:
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
