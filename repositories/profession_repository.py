from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from models.profession import Profession


def list_active_professions(db: Session) -> list[Profession]:
    q = (
        select(Profession)
        .where(Profession.is_active.is_(True))
        .order_by(Profession.id.asc())
    )
    return list(db.execute(q).scalars().all())


def get_profession_by_id(db: Session, profession_id: int) -> Profession | None:
    return db.get(Profession, profession_id)


def require_active_profession(db: Session, profession_id: int) -> Profession:
    p = get_profession_by_id(db, profession_id)
    if p is None or not p.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Профессия не найдена или отключена. Доступные: GET /professions/",
        )
    return p


def list_active_profession_ids(db: Session) -> set[int]:
    return {p.id for p in list_active_professions(db)}
