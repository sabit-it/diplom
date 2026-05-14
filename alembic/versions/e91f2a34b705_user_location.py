"""e91f2a34b705 user location

Revision ID: e91f2a34b705
Revises: c1d2e3f40567
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e91f2a34b705"
down_revision: Union[str, None] = "c1d2e3f40567"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("lng", sa.Numeric(precision=9, scale=6), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("location_updated_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "location_updated_at")
    op.drop_column("users", "lng")
    op.drop_column("users", "lat")
