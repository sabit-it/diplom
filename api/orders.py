from typing import Union
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from core.database import get_db
from core.dependencies import get_current_active_user, require_employer, require_worker
from models.user import User
from schemas.order import (
    OfferDeclinedResult,
    OfferRespondRequest,
    OrderAcceptedNotification,
    OrderCreate,
    OrderCreateResult,
    OrderParticipantView,
    OrderSummary,
    PendingOfferForWorker,
)
from services.order_service import (
    cancel_order,
    complete_order,
    create_order_with_dispatch,
    get_order_participant_view,
    list_orders_for_user,
    list_pending_offers_for_worker,
    repeat_order,
    respond_to_offer,
)
from utils.enums import OrderStatus

router = APIRouter(prefix="/orders", tags=["Заказы"])


@router.post(
    "/",
    response_model=OrderCreateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Создать заказ и разослать первое предложение",
    description=(
        "Доступно только роли **employer**. Поле **`profession_id`** должно совпадать с **активной** записью "
        "из **`GET /professions/`** (иначе 400). Создаётся заказ со статусом `pending_offer`, рассчитывается `total_price`. "
        "Система ищет ближайшего **онлайн**‑исполнителя (`PATCH /workers/me/line`) с той же профессией в профиле "
        "и известными координатами (приоритет — `worker_profiles`, иначе последняя позиция пользователя). "
        "Создаётся запись `order_offers` со статусом `sent`. Если подходящих нет — `no_workers_available`, "
        "`active_offer_id` = null и текст в `message`. "
        "При успешном подборе исполнителю отправляется email‑уведомление; при отсутствии кандидатов — заказчику."
    ),
)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
    employer: User = Depends(require_employer),
) -> OrderCreateResult:
    return create_order_with_dispatch(db, employer, payload)


@router.get(
    "/my",
    response_model=list[OrderSummary],
    summary="Моя история заказов",
    description=(
        "Для **employer** — заказы, которые он создавал. "
        "Для **worker** — заказы, в которых он был назначен исполнителем. "
        "Опциональный параметр `status` фильтрует по статусу (`pending_offer`, `assigned`, `completed`, `cancelled`, `no_workers_available`). "
        "Результат отсортирован по убыванию даты создания."
    ),
)
def list_my_orders(
    status: OrderStatus | None = Query(default=None, description="Фильтр по статусу заказа."),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> list[OrderSummary]:
    return list_orders_for_user(db, user, status_filter=status.value if status else None)


@router.get(
    "/pending-offers",
    response_model=list[PendingOfferForWorker],
    summary="Мои входящие предложения",
    description=(
        "Только для **worker**. Возвращает список активных предложений (`sent`), по которым заказ ещё в "
        "ожидании ответа (`pending_offer`). Каждый элемент содержит краткие данные предложения и заказа."
    ),
)
def list_my_pending_offers(
    db: Session = Depends(get_db),
    worker: User = Depends(require_worker),
) -> list[PendingOfferForWorker]:
    return list_pending_offers_for_worker(db, worker)


@router.patch(
    "/{order_id}/complete",
    response_model=OrderSummary,
    summary="Завершить заказ (перед отзывами)",
    description=(
        "Доступно **заказчику** или **назначенному исполнителю**, пока заказ в статусе **assigned**. "
        "Переводит заказ в **completed** и увеличивает счётчик `completed_orders` у профиля исполнителя. "
        "После этого участники могут оставить отзывы (`POST /reviews/`). "
        "Обоим участникам отправляется email‑уведомление о завершении."
    ),
)
def complete_order_endpoint(
    order_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> OrderSummary:
    return complete_order(db, user, order_id)


@router.get(
    "/{order_id}",
    response_model=OrderParticipantView,
    summary="Получить заказ по id",
    description=(
        "Доступ: владелец заказа (**employer_id**) или назначенный исполнитель (**assigned_worker_id**). "
        "После принятия заказа в `assigned_worker` возвращаются публичные данные исполнителя и его геопозиция "
        "(для заказчика — чтобы увидеть кого назначили; для исполнителя — подтверждение контекста)."
    ),
)
def read_order(
    order_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_active_user),
) -> OrderParticipantView:
    return get_order_participant_view(db, user=user, order_id=order_id)


@router.post(
    "/{order_id}/repeat",
    response_model=OrderCreateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Повторить заказ",
    description=(
        "Создаёт новый заказ с теми же параметрами (профессия, название, адрес, стоимость), "
        "что и указанный. `scheduled_at` сбрасывается — заказ размещается немедленно. "
        "Доступно только **заказчику** — владельцу исходного заказа."
    ),
)
def repeat_order_endpoint(
    order_id: UUID,
    db: Session = Depends(get_db),
    employer: User = Depends(require_employer),
) -> OrderCreateResult:
    return repeat_order(db, employer, order_id)


@router.patch(
    "/{order_id}/cancel",
    response_model=OrderSummary,
    summary="Отменить заказ",
    description=(
        "Доступно только **заказчику** (владельцу заказа). "
        "Заказ можно отменить в статусах **pending_offer**, **no_workers_available** и **assigned**. "
        "При отмене уже принятого (`assigned`) заказа исполнитель получает email‑уведомление."
    ),
)
def cancel_order_endpoint(
    order_id: UUID,
    db: Session = Depends(get_db),
    employer: User = Depends(require_employer),
) -> OrderSummary:
    return cancel_order(db, employer, order_id)


@router.post(
    "/offers/{offer_id}/respond",
    response_model=Union[OrderAcceptedNotification, OfferDeclinedResult],
    summary="Ответить на предложение (принять / отказать)",
    description=(
        "Только для **worker**, которому адресовано это предложение. "
        "**accept=true** — заказ переходит в `assigned`, исполнитель фиксируется в заказе; тело ответа содержит "
        "полный снимок заказа (включая адрес и координаты места работ) и объект исполнителя с рейтингом и гео. "
        "**accept=false** — предложение помечается отклонённым; если есть следующий кандидат, создаётся новое "
        "предложение, его id в `next_offer_id`; если кандидатов не осталось — `next_offer_id` null, статус заказа "
        "`no_workers_available`. В обоих случаях заказчику и следующему исполнителю отправляются email‑уведомления."
    ),
)
def respond_offer(
    offer_id: UUID,
    payload: OfferRespondRequest,
    db: Session = Depends(get_db),
    worker: User = Depends(require_worker),
) -> OrderAcceptedNotification | OfferDeclinedResult:
    return respond_to_offer(db, worker=worker, offer_id=offer_id, accept=payload.accept)
