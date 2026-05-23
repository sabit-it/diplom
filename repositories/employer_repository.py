import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.employer_profile import EmployerProfile


def get_employer_profile_by_user_id(db: Session, user_id: uuid.UUID) -> EmployerProfile | None:
    return db.execute(
        select(EmployerProfile).where(EmployerProfile.user_id == user_id)
    ).scalar_one_or_none()


def persist_employer_profile(db: Session, profile: EmployerProfile) -> EmployerProfile:
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
