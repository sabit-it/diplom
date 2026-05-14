from decimal import Decimal

from sqlalchemy.orm import Session

from repositories.profession_repository import require_active_profession


def reference_rate_for_profession(db: Session, profession_id: int) -> Decimal:
    p = require_active_profession(db, profession_id)
    return p.hourly_rate
