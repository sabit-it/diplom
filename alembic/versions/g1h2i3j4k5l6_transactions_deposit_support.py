"""transactions: nullable order_id + type column for deposit support

Revision ID: g1h2i3j4k5l6
Revises: f8a3c1d2e4b5
Create Date: 2026-05-27

"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "g1h2i3j4k5l6"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Снимаем NOT NULL с order_id, чтобы депозитные транзакции не ссылались на заказ.
    op.alter_column("transactions", "order_id", nullable=True)

    op.add_column(
        "transactions",
        sa.Column(
            "type",
            sa.String(32),
            nullable=False,
            server_default="order_settlement",
        ),
    )


def downgrade() -> None:
    op.drop_column("transactions", "type")
    # Обратно делаем NOT NULL только если все строки имеют order_id
    op.alter_column("transactions", "order_id", nullable=False)
