import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models.transaction import Transaction


def create_transaction(
    db: Session,
    *,
    order_id: uuid.UUID | None,
    payer_id: uuid.UUID,
    receiver_id: uuid.UUID,
    amount: Decimal,
    commission_amount: Decimal,
    tx_type: str = "order_settlement",
) -> Transaction:
    tx = Transaction(
        order_id=order_id,
        payer_id=payer_id,
        receiver_id=receiver_id,
        amount=amount,
        commission_amount=commission_amount,
        type=tx_type,
        status="completed",
    )
    db.add(tx)
    return tx


def list_transactions_for_user(
    db: Session,
    user_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
    tx_type: str | None = None,
) -> tuple[list[Transaction], int]:
    q = select(Transaction).where(
        or_(Transaction.payer_id == user_id, Transaction.receiver_id == user_id)
    )
    if tx_type is not None:
        q = q.where(Transaction.type == tx_type)
    total: int = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = list(
        db.execute(
            q.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
        ).scalars()
    )
    return rows, total


def summarize_transactions_for_user(
    db: Session,
    user_id: uuid.UUID,
) -> dict[str, Decimal]:
    def _sum(tx_type: str, as_receiver: bool = False, net: bool = False) -> Decimal:
        # net=True: worker receives amount - commission_amount (after platform fee)
        agg = func.coalesce(
            func.sum(Transaction.amount - Transaction.commission_amount if net else Transaction.amount),
            0,
        )
        q = select(agg).where(
            or_(Transaction.payer_id == user_id, Transaction.receiver_id == user_id)
        ).where(Transaction.type == tx_type)
        if as_receiver:
            q = q.where(Transaction.receiver_id == user_id, Transaction.payer_id != user_id)
        return Decimal(str(db.execute(q).scalar_one()))

    return {
        "total_deposited": _sum("deposit"),
        "total_withdrawn": _sum("withdrawal"),
        "total_earned": _sum("order_settlement", as_receiver=True, net=True),
        "total_spent": _sum("order_settlement"),
    }
