import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.order import Order
from models.user import User
from models.worker_profile import WorkerProfile
from repositories.offer_repository import (
    create_offer,
    get_offer_by_id,
    list_pending_sent_offers_for_worker,
    worker_ids_with_offers_for_order,
)
from repositories.order_repository import (
    create_order,
    get_order_by_id,
    list_orders_for_employer,
    list_orders_for_worker,
    save_order,
)
from repositories.profession_repository import require_active_profession
from repositories.worker_repository import find_nearest_available_worker
from schemas.order import (
    AssignedWorkerOut,
    OfferDeclinedResult,
    OfferSummary,
    OrderAcceptedNotification,
    OrderCreate,
    OrderCreateResult,
    OrderParticipantView,
    OrderSummary,
    PendingOfferForWorker,
    WorkerLocationOut,
)
from utils.enums import OfferStatus, OrderStatus, UserRole
from services.payment_service import settle_order
from services.email_service import (
    notify_employer_worker_accepted,
    notify_employer_worker_declined,
    notify_no_workers,
    notify_order_completed,
    notify_worker_new_offer,
    notify_worker_order_cancelled,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _order_summary(order: Order) -> OrderSummary:
    return OrderSummary.model_validate(order)


def _assigned_worker_payload(user: User, profile: WorkerProfile | None) -> AssignedWorkerOut:
    if profile is not None and profile.current_lat is not None and profile.current_lng is not None:
        loc = WorkerLocationOut(lat=profile.current_lat, lng=profile.current_lng, source="worker_profile")
    elif user.lat is not None and user.lng is not None:
        loc = WorkerLocationOut(lat=user.lat, lng=user.lng, source="user")
    else:
        loc = WorkerLocationOut(lat=None, lng=None, source="user")

    return AssignedWorkerOut(
        id=user.id,
        email=user.email,
        phone=user.phone,
        last_name=user.last_name,
        first_name=user.first_name,
        patronymic=user.patronymic,
        role=UserRole(user.role),
        photo_url=user.photo_url,
        rating_avg=profile.rating_avg if profile else None,
        reviews_count=profile.reviews_count if profile else 0,
        completed_orders=profile.completed_orders if profile else 0,
        location=loc,
    )


def create_order_with_dispatch(
    db: Session,
    employer: User,
    payload: OrderCreate,
) -> OrderCreateResult:
    require_active_profession(db, payload.profession_id)

    if employer.balance < 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Создание заказа недоступно при отрицательном балансе. Пополните баланс.",
        )

    total = payload.total_price
    order = create_order(
        db,
        employer_id=employer.id,
        profession_id=payload.profession_id,
        title=payload.title.strip(),
        description=(payload.description.strip() if payload.description else None),
        hours=payload.hours,
        hourly_rate=payload.hourly_rate,
        total_price=total,
        address=payload.address.strip(),
        lat=payload.lat,
        lng=payload.lng,
        scheduled_at=payload.scheduled_at,
        status=OrderStatus.pending_offer.value,
    )

    exclude: set[uuid.UUID] = set()
    nearest = find_nearest_available_worker(
        db,
        profession_id=payload.profession_id,
        order_lat=payload.lat,
        order_lng=payload.lng,
        exclude_worker_ids=exclude,
    )

    if nearest is None:
        order.status = OrderStatus.no_workers_available.value
        save_order(db, order)
        notify_no_workers(employer.email, order.title)
        return OrderCreateResult(
            order=_order_summary(order),
            active_offer_id=None,
            message="Нет доступных работников с геопозицией и статусом «онлайн».",
        )

    user_w, _profile_w, dist_m = nearest
    offer = create_offer(
        db,
        order_id=order.id,
        worker_id=user_w.id,
        distance_meters=int(round(dist_m)),
    )
    notify_worker_new_offer(user_w.email, user_w.formatted_fio, order.title, order.address)
    return OrderCreateResult(
        order=_order_summary(order),
        active_offer_id=offer.id,
        message=None,
    )


def _dispatch_next_after_decline(db: Session, order: Order) -> uuid.UUID | None:
    exclude = worker_ids_with_offers_for_order(db, order.id)
    nearest = find_nearest_available_worker(
        db,
        profession_id=order.profession_id,
        order_lat=order.lat,
        order_lng=order.lng,
        exclude_worker_ids=exclude,
    )
    if nearest is None:
        order.status = OrderStatus.no_workers_available.value
        save_order(db, order)
        return None

    user_w, _profile_w, dist_m = nearest
    offer = create_offer(
        db,
        order_id=order.id,
        worker_id=user_w.id,
        distance_meters=int(round(dist_m)),
    )
    notify_worker_new_offer(user_w.email, user_w.formatted_fio, order.title, order.address)
    return offer.id


def respond_to_offer(
    db: Session,
    *,
    worker: User,
    offer_id: uuid.UUID,
    accept: bool,
) -> OrderAcceptedNotification | OfferDeclinedResult:
    offer = get_offer_by_id(db, offer_id)
    if offer is None or offer.worker_id != worker.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )

    order = get_order_by_id(db, offer.order_id)
    if order is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order not found",
        )

    if order.status != OrderStatus.pending_offer.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Order is not awaiting acceptance",
        )

    if offer.status != OfferStatus.sent.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This offer is no longer active",
        )

    employer = db.get(User, order.employer_id)

    if accept:
        existing = db.execute(
            select(Order).where(
                Order.assigned_worker_id == worker.id,
                Order.status == OrderStatus.assigned.value,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="У вас уже есть активный заказ",
            )

    if accept:
        offer.status = OfferStatus.accepted.value
        offer.responded_at = _now()
        order.assigned_worker_id = worker.id
        order.status = OrderStatus.assigned.value
        db.add(offer)
        db.add(order)
        db.commit()
        db.refresh(order)
        db.refresh(offer)

        wp = db.execute(
            select(WorkerProfile).where(WorkerProfile.user_id == worker.id)
        ).scalar_one_or_none()
        if wp is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Worker profile missing",
            )
        if employer:
            notify_employer_worker_accepted(employer.email, order.title, worker.formatted_fio)
        return OrderAcceptedNotification(
            order=_order_summary(order),
            worker=_assigned_worker_payload(worker, wp),
        )

    offer.status = OfferStatus.declined.value
    offer.responded_at = _now()
    db.add(offer)
    db.commit()
    db.refresh(order)

    next_id = _dispatch_next_after_decline(db, order)
    db.refresh(order)
    if employer:
        notify_employer_worker_declined(employer.email, order.title, next_found=next_id is not None)
    msg = (
        "Предложение отправлено следующему ближайшему работнику."
        if next_id
        else "Нет других доступных работников."
    )
    return OfferDeclinedResult(
        order=_order_summary(order),
        next_offer_id=next_id,
        message=msg,
    )


def get_order_for_participant(
    db: Session,
    *,
    user: User,
    order_id: uuid.UUID,
) -> tuple[OrderSummary, AssignedWorkerOut | None]:
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.employer_id != user.id and order.assigned_worker_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    worker_out: AssignedWorkerOut | None = None
    if order.assigned_worker_id is not None:
        wu = db.get(User, order.assigned_worker_id)
        if wu is not None:
            wp = db.execute(
                select(WorkerProfile).where(WorkerProfile.user_id == wu.id)
            ).scalar_one_or_none()
            worker_out = _assigned_worker_payload(wu, wp)

    return _order_summary(order), worker_out


def get_order_participant_view(
    db: Session,
    *,
    user: User,
    order_id: uuid.UUID,
) -> OrderParticipantView:
    order_s, worker_o = get_order_for_participant(db, user=user, order_id=order_id)
    return OrderParticipantView(order=order_s, assigned_worker=worker_o)


def list_pending_offers_for_worker(
    db: Session,
    worker: User,
) -> list[PendingOfferForWorker]:
    offers = list_pending_sent_offers_for_worker(db, worker.id)
    out: list[PendingOfferForWorker] = []
    for off in offers:
        o = get_order_by_id(db, off.order_id)
        if o is None or o.status != OrderStatus.pending_offer.value:
            continue
        out.append(
            PendingOfferForWorker(
                offer=OfferSummary.model_validate(off),
                order=_order_summary(o),
            )
        )
    return out


def complete_order(db: Session, user: User, order_id: uuid.UUID) -> OrderSummary:
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.employer_id != user.id and order.assigned_worker_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    if order.status != OrderStatus.assigned.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Завершить можно только заказ в статусе assigned",
        )

    if order.assigned_worker_id is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Нет назначенного исполнителя",
        )

    order.status = OrderStatus.completed.value
    db.add(order)

    wp = db.execute(
        select(WorkerProfile).where(WorkerProfile.user_id == order.assigned_worker_id)
    ).scalar_one_or_none()
    if wp is not None:
        wp.completed_orders = int(wp.completed_orders) + 1
        db.add(wp)

    settle_order(db, order)

    db.commit()
    db.refresh(order)
    if wp is not None:
        db.refresh(wp)

    employer = db.get(User, order.employer_id)
    if employer:
        notify_order_completed(employer.email, employer.formatted_fio, order.title)
    worker_user = db.get(User, order.assigned_worker_id)
    if worker_user:
        notify_order_completed(worker_user.email, worker_user.formatted_fio, order.title)

    return _order_summary(order)


def cancel_order(db: Session, employer: User, order_id: uuid.UUID) -> OrderSummary:
    order = get_order_by_id(db, order_id)
    if order is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if order.employer_id != employer.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    cancellable = {
        OrderStatus.pending_offer.value,
        OrderStatus.no_workers_available.value,
        OrderStatus.assigned.value,
    }
    if order.status not in cancellable:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Отменить можно только заказ в статусе pending_offer, no_workers_available или assigned",
        )

    was_assigned = order.status == OrderStatus.assigned.value
    worker_id = order.assigned_worker_id

    order.status = OrderStatus.cancelled.value
    db.add(order)
    db.commit()
    db.refresh(order)

    if was_assigned and worker_id is not None:
        worker_user = db.get(User, worker_id)
        if worker_user:
            notify_worker_order_cancelled(worker_user.email, worker_user.formatted_fio, order.title)

    return _order_summary(order)


def list_orders_for_user(
    db: Session,
    user: User,
    *,
    status_filter: str | None = None,
) -> list[OrderSummary]:
    from utils.enums import UserRole
    if user.role == UserRole.employer.value:
        orders = list_orders_for_employer(db, user.id, status=status_filter)
    else:
        orders = list_orders_for_worker(db, user.id, status=status_filter)
    return [_order_summary(o) for o in orders]


def repeat_order(db: Session, employer: User, order_id: uuid.UUID) -> OrderCreateResult:
    original = get_order_by_id(db, order_id)
    if original is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if original.employer_id != employer.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")

    payload = OrderCreate(
        profession_id=original.profession_id,
        title=original.title,
        description=original.description,
        hours=original.hours,
        hourly_rate=original.hourly_rate,
        address=original.address,
        lat=original.lat,
        lng=original.lng,
        scheduled_at=None,
    )
    return create_order_with_dispatch(db, employer, payload)
