import uuid
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from models.transaction import Transaction


def create_transaction(
    db: Session,
    *,
    order_id: uuid.UUID,
    payer_id: uuid.UUID,
    receiver_id: uuid.UUID,
    amount: Decimal,
    commission_amount: Decimal,
) -> Transaction:
    tx = Transaction(
        order_id=order_id,
        payer_id=payer_id,
        receiver_id=receiver_id,
        amount=amount,
        commission_amount=commission_amount,
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
) -> tuple[list[Transaction], int]:
    q = select(Transaction).where(
        or_(Transaction.payer_id == user_id, Transaction.receiver_id == user_id)
    )
    total: int = db.execute(select(func.count()).select_from(q.subquery())).scalar_one()
    rows = list(
        db.execute(
            q.order_by(Transaction.created_at.desc()).offset(offset).limit(limit)
        ).scalars()
    )
    return rows, total
