import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from core.database import get_db
from core.security import TokenValidationError, decode_access_token
from models.user import User
from repositories.user_repository import get_user_by_id

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


def get_token_payload(token: str = Depends(oauth2_scheme)) -> dict:
    try:
        return decode_access_token(token)
    except TokenValidationError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_user_id(payload: dict = Depends(get_token_payload)) -> uuid.UUID:
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return uuid.UUID(str(sub))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid subject in token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


def get_current_user(
    user_id: uuid.UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )
    if user.is_blocked:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Аккаунт заблокирован.",
        )
    return user


def require_admin(user: User = Depends(get_current_active_user)) -> User:
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администраторов.",
        )
    return user


def require_employer(user: User = Depends(get_current_active_user)) -> User:
    from utils.enums import UserRole

    if user.role != UserRole.employer.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Employers only",
        )
    return user


def require_worker(user: User = Depends(get_current_active_user)) -> User:
    from utils.enums import UserRole

    if user.role != UserRole.worker.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Workers only",
        )
    return user
