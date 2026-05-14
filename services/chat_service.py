from sqlalchemy.orm import Session

from repositories.profession_repository import get_profession_by_id, require_active_profession


def ensure_profession_for_chat_context(db: Session, profession_id: int):
    return require_active_profession(db, profession_id)


def profession_display_name(db: Session, profession_id: int) -> str | None:
    p = get_profession_by_id(db, profession_id)
    if p is None or not p.is_active:
        return None
    return p.name
