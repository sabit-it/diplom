import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Text, Boolean, DateTime, Numeric, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WorkerProfile(Base):
    __tablename__ = "worker_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    profession_id: Mapped[int] = mapped_column(ForeignKey("professions.id"), nullable=False)

    about: Mapped[str | None] = mapped_column(Text, nullable=True)

    rating_avg: Mapped[Decimal] = mapped_column(Numeric(3, 2), default=0, nullable=False)
    reviews_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_orders: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    max_distance_km: Mapped[int | None] = mapped_column(Integer, nullable=True)

    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    current_lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6), nullable=True)
    last_location_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)