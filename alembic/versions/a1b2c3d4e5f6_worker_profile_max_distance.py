"""worker_profile: add max_distance_km

Revision ID: a1b2c3d4e5f6
Revises: f8a3c1d2e4b5
Create Date: 2026-05-21

"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f8a3c1d2e4b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "worker_profiles",
        sa.Column("max_distance_km", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("worker_profiles", "max_distance_km")
