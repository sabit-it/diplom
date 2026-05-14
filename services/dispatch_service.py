from sqlalchemy.orm import Session

from repositories.profession_repository import list_active_profession_ids, require_active_profession


def ensure_profession_for_dispatch(db: Session, profession_id: int):
    return require_active_profession(db, profession_id)


def active_profession_id_set(db: Session) -> set[int]:
    return list_active_profession_ids(db)
