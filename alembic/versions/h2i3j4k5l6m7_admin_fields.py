"""users: add is_blocked and is_admin fields

Revision ID: h2i3j4k5l6m7
Revises: g1h2i3j4k5l6
Create Date: 2026-05-30

"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "h2i3j4k5l6m7"
down_revision: Union[str, None] = "g1h2i3j4k5l6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("users", "is_admin")
    op.drop_column("users", "is_blocked")
