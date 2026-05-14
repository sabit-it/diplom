from sqlalchemy.orm import Session

from repositories.profession_repository import require_active_profession


def ensure_profession_for_offer(db: Session, profession_id: int):
    return require_active_profession(db, profession_id)
