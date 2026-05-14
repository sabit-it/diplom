"""user photo_url

Revision ID: b4c8a1f02e7d
Revises: 6eb1b7e65c62
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b4c8a1f02e7d"
down_revision: Union[str, None] = "6eb1b7e65c62"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("photo_url", sa.String(length=512), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "photo_url")
