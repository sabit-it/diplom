import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, DateTime, String, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class OrderOffer(Base):
    __tablename__ = "order_offers"

    __table_args__ = (
        UniqueConstraint("order_id", "worker_id", name="uq_order_offer_order_worker"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    order_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("orders.id"), nullable=False)
    worker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    distance_meters: Mapped[int] = mapped_column(Integer, nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="sent", nullable=False)

    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)