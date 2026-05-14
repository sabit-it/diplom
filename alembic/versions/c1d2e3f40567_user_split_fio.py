"""user split full_name into last first patronymic

Revision ID: c1d2e3f40567
Revises: b4c8a1f02e7d
Create Date: 2026-04-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c1d2e3f40567"
down_revision: Union[str, None] = "b4c8a1f02e7d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("last_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("first_name", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("patronymic", sa.String(length=255), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE users
            SET
                last_name = '',
                first_name = TRIM(COALESCE(full_name, '')),
                patronymic = NULL
        """)
    )

    op.alter_column(
        "users",
        "last_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )
    op.alter_column(
        "users",
        "first_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_column("users", "full_name")


def downgrade() -> None:
    op.add_column(
        "users",
        sa.Column("full_name", sa.String(length=255), nullable=True),
    )

    conn = op.get_bind()
    conn.execute(
        sa.text("""
            UPDATE users
            SET full_name = TRIM(CONCAT_WS(' ',
                NULLIF(TRIM(last_name), ''),
                NULLIF(TRIM(first_name), ''),
                NULLIF(TRIM(patronymic), '')
            ))
        """)
    )

    conn.execute(
        sa.text("""
            UPDATE users
            SET full_name = '-'
            WHERE full_name IS NULL OR TRIM(full_name) = ''
        """)
    )

    op.alter_column(
        "users",
        "full_name",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_column("users", "patronymic")
    op.drop_column("users", "first_name")
    op.drop_column("users", "last_name")
