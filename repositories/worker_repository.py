import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.order import Order
from models.order_offer import OrderOffer
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.profession_repository import require_active_profession
from utils.enums import OfferStatus, OrderStatus, UserRole
from utils.geo import haversine_meters


def get_busy_worker_ids(db: Session) -> set[uuid.UUID]:
    # Работник занят в двух случаях:
    # 1. он уже принял заказ и работает (assigned)
    # 2. ему отправлен оффер и он ещё не ответил (sent)
    # Оба случая исключаем — нельзя слать новый оффер, пока предыдущий висит в воздухе.
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

    # Глобально занятые (assigned/sent по любому заказу) + уже получавшие
    # оффер по этому конкретному заказу (чтоб не слать второй раз).
    busy_ids = get_busy_worker_ids(db)
    skip = exclude_worker_ids | busy_ids

    # Базовый фильтр: роль, профессия, онлайн. Координаты проверяем вручную —
    # они хранятся в двух местах (profile.current_* или user.lat/lng).
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
            # Нет координат — работник не участвует в подборе по гео.
            continue
        wlat, wlng = coords
        dist = haversine_meters(order_lat, order_lng, wlat, wlng)
        # Если работник задал максимальное расстояние — заказы дальше него не предлагаем.
        if profile.max_distance_km is not None and dist > profile.max_distance_km * 1000:
            continue
        candidates.append((user, profile, dist))

    if not candidates:
        return None
    # Сортируем по расстоянию и берём ближайшего.
    candidates.sort(key=lambda x: x[2])
    user, profile, dist = candidates[0]
    return user, profile, dist


def list_workers_catalog(
    db: Session,
    *,
    profession_id: int | None,
    min_rating: Decimal | None,
    is_online: bool | None,
    limit: int,
    offset: int,
) -> tuple[list[tuple[User, WorkerProfile]], int]:
    q = (
        select(User, WorkerProfile)
        .join(WorkerProfile, WorkerProfile.user_id == User.id)
        .where(User.role == UserRole.worker.value)
    )
    if profession_id is not None:
        q = q.where(WorkerProfile.profession_id == profession_id)
    if min_rating is not None:
        q = q.where(WorkerProfile.rating_avg >= min_rating)
    if is_online is not None:
        q = q.where(WorkerProfile.is_online.is_(is_online))

    total: int = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()

    q = q.order_by(WorkerProfile.rating_avg.desc(), WorkerProfile.completed_orders.desc())
    q = q.offset(offset).limit(limit)

    rows = list(db.execute(q).all())
    return rows, total


def get_worker_profile_by_user_id(db: Session, user_id: uuid.UUID) -> WorkerProfile | None:
    q = select(WorkerProfile).where(WorkerProfile.user_id == user_id)
    return db.execute(q).scalar_one_or_none()


def persist_worker_profile(db: Session, profile: WorkerProfile) -> WorkerProfile:
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
