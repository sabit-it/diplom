from decimal import Decimal

from sqlalchemy import String, Boolean, Numeric, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Profession(Base):
    __tablename__ = "professions"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    rate_unit: Mapped[str] = mapped_column(String(20), nullable=False, default="hour")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)