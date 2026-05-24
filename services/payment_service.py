from decimal import Decimal, ROUND_HALF_UP
import uuid

from sqlalchemy.orm import Session

from core.config import settings
from models.order import Order
from models.user import User
from repositories.transaction_repository import create_transaction, list_transactions_for_user
from schemas.transaction import TransactionListOut, TransactionOut


def _commission_percent() -> Decimal:
    return Decimal(str(settings.PLATFORM_COMMISSION_PERCENT))


def settle_order(db: Session, order: Order) -> None:
    """Создаёт транзакцию и обновляет балансы при завершении заказа.

    Employer balance уменьшается на полную сумму заказа.
    Worker balance увеличивается на сумму за вычетом комиссии платформы.
    Вызывать внутри той же транзакции БД, что и смена статуса заказа.
    """
    employer = db.get(User, order.employer_id)
    worker = db.get(User, order.assigned_worker_id)
    if employer is None or worker is None:
        return

    total: Decimal = order.total_price
    commission: Decimal = (total * _commission_percent() / Decimal("100")).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )
    worker_amount: Decimal = total - commission

    employer.balance = employer.balance - total
    worker.balance = worker.balance + worker_amount
    db.add(employer)
    db.add(worker)

    create_transaction(
        db,
        order_id=order.id,
        payer_id=order.employer_id,
        receiver_id=order.assigned_worker_id,
        amount=total,
        commission_amount=commission,
    )


def list_my_transactions(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
) -> TransactionListOut:
    rows, total = list_transactions_for_user(db, user.id, limit=limit, offset=offset)
    items = [TransactionOut.model_validate(t) for t in rows]
    return TransactionListOut(items=items, total=total, limit=limit, offset=offset)
