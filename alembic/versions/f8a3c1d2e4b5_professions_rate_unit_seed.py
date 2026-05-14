"""professions rate_unit and seed catalog

Revision ID: f8a3c1d2e4b5
Revises: e91f2a34b705
Create Date: 2026-05-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f8a3c1d2e4b5"
down_revision: Union[str, None] = "e91f2a34b705"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "professions",
        sa.Column(
            "rate_unit",
            sa.String(length=20),
            nullable=False,
            server_default="hour",
        ),
    )
    op.alter_column("professions", "rate_unit", server_default=None)

    op.execute(
        sa.text(
            """
            INSERT INTO professions (id, name, hourly_rate, is_active, rate_unit) VALUES
            (1, 'Уборка квартир', 150, true, 'square_meter'),
            (2, 'Мытьё окон', 400, true, 'window_sash'),
            (3, 'Сборка / разборка мебели', 700, true, 'hour'),
            (4, 'Копка грядок / прополка', 500, true, 'hour'),
            (5, 'Погрузочно-разгрузочные работы', 600, true, 'hour'),
            (6, 'Мелкий ремонт сантехники', 1000, true, 'hour'),
            (7, 'Мелкий ремонт бытовой техники', 1000, true, 'hour'),
            (8, 'Выгул собак', 400, true, 'hour'),
            (9, 'Уборка снега', 500, true, 'hour'),
            (10, 'Помощь в быту (почасовая)', 500, true, 'hour')
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                hourly_rate = EXCLUDED.hourly_rate,
                is_active = EXCLUDED.is_active,
                rate_unit = EXCLUDED.rate_unit
            """
        )
    )


def downgrade() -> None:
    op.drop_column("professions", "rate_unit")
