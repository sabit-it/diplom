from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from models.employer_profile import EmployerProfile
from models.user import User
from repositories.employer_repository import (
    get_employer_profile_by_user_id,
    persist_employer_profile,
)
from schemas.employer import EmployerProfileOut, EmployerProfileUpsert
from utils.enums import UserRole


def get_my_employer_profile(db: Session, user: User) -> EmployerProfileOut:
    if user.role != UserRole.employer.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employers only")
    ep = get_employer_profile_by_user_id(db, user.id)
    if ep is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Профиль заказчика не создан. Используйте PUT /employers/me",
        )
    return EmployerProfileOut.model_validate(ep)


def upsert_my_employer_profile(
    db: Session,
    user: User,
    payload: EmployerProfileUpsert,
) -> EmployerProfileOut:
    if user.role != UserRole.employer.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Employers only")

    company_name = (
        payload.company_name.strip()
        if payload.company_name and payload.company_name.strip()
        else None
    )
    address = (
        payload.address.strip()
        if payload.address and payload.address.strip()
        else None
    )

    ep = get_employer_profile_by_user_id(db, user.id)
    if ep is None:
        ep = EmployerProfile(
            user_id=user.id,
            company_name=company_name,
            address=address,
        )
    else:
        ep.company_name = company_name
        ep.address = address

    persist_employer_profile(db, ep)
    return EmployerProfileOut.model_validate(ep)
