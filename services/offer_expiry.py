"""
Фоновый сервис: истечение офферов по таймауту (30 секунд).

Каждые 5 секунд ищет офферы со статусом 'sent', созданные более 30 секунд
назад, и обрабатывает их: помечает как expired, затем пытается найти
следующего ближайшего исполнителя или уведомляет заказчика об отсутствии
кандидатов.

PostgreSQL SELECT ... FOR UPDATE SKIP LOCKED гарантирует, что при запуске
нескольких воркеров (uvicorn --workers N) каждый оффер обрабатывается ровно
одним процессом.
"""
import logging
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.database import engine
from models.order import Order
from models.order_offer import OrderOffer
from models.user import User
from repositories.offer_repository import worker_ids_with_offers_for_order
from repositories.worker_repository import find_nearest_available_worker
from services.email_service import notify_employer_offer_timed_out, notify_worker_new_offer
from utils.enums import OfferStatus, OrderStatus

logger = logging.getLogger(__name__)

_OFFER_TIMEOUT_SECONDS = 30
_POLL_INTERVAL_SECONDS = 5


# ---------------------------------------------------------------------------
# Core logic (public — can be injected in tests with an existing session)
# ---------------------------------------------------------------------------

def expire_offer(db: Session, offer_id: uuid.UUID) -> bool:
    """
    Mark a single sent offer as expired and dispatch to the next worker (or
    update the order status if none are left).

    Does NOT commit — the caller is responsible for committing or the session
    will autoflush on the next query.

    Returns True if the offer was found and processed, False if already gone.
    """
    offer = db.get(OrderOffer, offer_id)
    if offer is None or offer.status != OfferStatus.sent.value:
        return False

    _handle_expired_offer(db, offer)
    return True


def _handle_expired_offer(db: Session, offer: OrderOffer) -> None:
    offer.status = OfferStatus.expired.value
    offer.responded_at = datetime.now(timezone.utc)

    order = db.get(Order, offer.order_id)
    # Если заказ уже не ждёт ответа (например, его успели отменить или принять
    # через другой оффер) — просто фиксируем истечение и выходим.
    if order is None or order.status != OrderStatus.pending_offer.value:
        return

    employer = db.get(User, order.employer_id)
    # Не слать оффер тем, кто уже отказал или у кого он истёк по этому заказу.
    exclude = worker_ids_with_offers_for_order(db, order.id)

    try:
        nearest = find_nearest_available_worker(
            db,
            profession_id=order.profession_id,
            order_lat=order.lat,
            order_lng=order.lng,
            exclude_worker_ids=exclude,
        )
    except HTTPException:
        # Профессия могла быть деактивирована после создания заказа.
        nearest = None

    if nearest is None:
        # Больше никого нет — заказ переходит в «нет кандидатов».
        order.status = OrderStatus.no_workers_available.value
        if employer:
            notify_employer_offer_timed_out(employer.email, order.title, next_found=False)
    else:
        user_w, _profile_w, dist_m = nearest
        new_offer = OrderOffer(
            order_id=order.id,
            worker_id=user_w.id,
            distance_meters=int(round(dist_m)),
        )
        db.add(new_offer)
        notify_worker_new_offer(user_w.email, user_w.formatted_fio, order.title, order.address)
        if employer:
            notify_employer_offer_timed_out(employer.email, order.title, next_found=True)


# ---------------------------------------------------------------------------
# Production runner (with own sessions + SKIP LOCKED)
# ---------------------------------------------------------------------------

def _process_one(offer_id: uuid.UUID) -> None:
    with Session(engine) as session:
        with session.begin():
            # FOR UPDATE SKIP LOCKED: если оффер уже захвачен другим процессом
            # uvicorn — пропускаем его, не ждём разблокировки. Каждый оффер
            # обрабатывается ровно один раз даже при нескольких воркерах.
            offer = session.execute(
                select(OrderOffer)
                .where(
                    OrderOffer.id == offer_id,
                    OrderOffer.status == OfferStatus.sent.value,
                )
                .with_for_update(skip_locked=True)
            ).scalar_one_or_none()

            if offer is None:
                return  # Уже обработан другим процессом или принят/отклонён вручную.

            _handle_expired_offer(session, offer)


def _expire_due_offers() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=_OFFER_TIMEOUT_SECONDS)

    # Читаем только ID в отдельной сессии — так мы не держим открытую транзакцию
    # пока обрабатываем каждый оффер по очереди (каждый в своей сессии с SKIP LOCKED).
    with Session(engine) as session:
        expired_ids: list[uuid.UUID] = list(
            session.execute(
                select(OrderOffer.id).where(
                    OrderOffer.status == OfferStatus.sent.value,
                    OrderOffer.sent_at < cutoff,
                )
            ).scalars()
        )

    for offer_id in expired_ids:
        try:
            _process_one(offer_id)
        except Exception:
            logger.exception("Failed to expire offer %s", offer_id)


def _expiry_loop() -> None:
    while True:
        try:
            _expire_due_offers()
        except Exception:
            logger.exception("Offer expiry loop error")
        time.sleep(_POLL_INTERVAL_SECONDS)


def start_expiry_thread() -> threading.Thread:
    thread = threading.Thread(target=_expiry_loop, daemon=True, name="offer-expiry")
    thread.start()
    logger.info(
        "Offer expiry thread started (timeout=%ds, poll=%ds)",
        _OFFER_TIMEOUT_SECONDS,
        _POLL_INTERVAL_SECONDS,
    )
    return thread
