from decimal import Decimal, ROUND_HALF_UP
import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.config import settings
from models.order import Order
from models.user import User
from repositories.transaction_repository import create_transaction, list_transactions_for_user, summarize_transactions_for_user
from schemas.transaction import DepositOut, TransactionListOut, TransactionOut, TransactionSummaryOut, WithdrawOut
from utils.enums import UserRole


def _commission_percent() -> Decimal:
    return Decimal(str(settings.PLATFORM_COMMISSION_PERCENT))


def settle_order(db: Session, order: Order) -> None:
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
        tx_type="order_settlement",
    )


def deposit_balance(db: Session, user: User, amount: Decimal) -> DepositOut:
    if user.role != UserRole.employer.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Пополнение баланса доступно только заказчикам.",
        )

    user.balance = user.balance + amount
    db.add(user)

    tx = create_transaction(
        db,
        order_id=None,
        payer_id=user.id,
        receiver_id=user.id,
        amount=amount,
        commission_amount=Decimal("0.00"),
        tx_type="deposit",
    )

    db.commit()
    db.refresh(user)
    db.refresh(tx)

    return DepositOut(
        transaction_id=tx.id,
        amount=amount,
        new_balance=user.balance,
    )


def withdraw_balance(db: Session, user: User, amount: Decimal, card_number: str) -> WithdrawOut:
    if user.role != UserRole.worker.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Вывод средств доступен только исполнителям.",
        )

    if user.balance < amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Недостаточно средств. Текущий баланс: {user.balance} ₽.",
        )

    user.balance = user.balance - amount
    db.add(user)

    tx = create_transaction(
        db,
        order_id=None,
        payer_id=user.id,
        receiver_id=user.id,
        amount=amount,
        commission_amount=Decimal("0.00"),
        tx_type="withdrawal",
    )

    db.commit()
    db.refresh(user)
    db.refresh(tx)

    return WithdrawOut(
        transaction_id=tx.id,
        amount=amount,
        new_balance=user.balance,
        card_last4=card_number[-4:],
    )


def list_my_transactions(
    db: Session,
    user: User,
    *,
    limit: int,
    offset: int,
    tx_type: str | None = None,
) -> TransactionListOut:
    rows, total = list_transactions_for_user(db, user.id, limit=limit, offset=offset, tx_type=tx_type)
    items = [TransactionOut.model_validate(t) for t in rows]
    return TransactionListOut(items=items, total=total, limit=limit, offset=offset)


def get_my_summary(db: Session, user: User) -> TransactionSummaryOut:
    totals = summarize_transactions_for_user(db, user.id)
    return TransactionSummaryOut(
        current_balance=user.balance,
        **totals,
    )
