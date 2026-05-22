from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from core.security import (
    access_token_ttl_seconds,
    create_access_token,
    get_password_hash,
    verify_password,
)
from models.user import User
from models.user import User
from repositories.user_repository import (
    create_user,
    get_user_by_email,
    get_user_by_phone,
    update_user_email,
    update_user_password,
    update_user_profile,
)
from schemas.auth import EmailChangeRequest, PasswordChangeRequest, TokenResponse, UserProfileUpdate, UserPublic


def _build_token_response(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        expires_in=access_token_ttl_seconds(),
    )


def register_user(
    db: Session,
    *,
    email: str,
    password: str,
    last_name: str,
    first_name: str,
    patronymic: str | None,
    role: str,
    phone: str | None = None,
    photo_url: str | None = None,
) -> TokenResponse:
    email = email.strip().lower()
    if get_user_by_email(db, email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
    if phone is not None and get_user_by_phone(db, phone):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Phone already registered",
        )

    normalized_photo = (
        photo_url.strip()
        if photo_url and photo_url.strip()
        else None
    )

    patronymic_normalized = (
        patronymic.strip()
        if patronymic and patronymic.strip()
        else None
    )

    user = create_user(
        db,
        email=email,
        password_hash=get_password_hash(password),
        last_name=last_name.strip(),
        first_name=first_name.strip(),
        patronymic=patronymic_normalized,
        role=role.strip(),
        phone=phone,
        photo_url=normalized_photo,
    )

    return _build_token_response(user)


def update_profile(db: Session, user: User, payload: UserProfileUpdate) -> User:
    # Различаем "поле не передано" (None) от "передано явно" (пустая строка → очистить).
    # Pydantic не даёт нам это напрямую, поэтому используем sentinel-логику в репозитории.
    raw = payload.model_dump(exclude_unset=True)
    return update_user_profile(
        db,
        user,
        first_name=raw.get("first_name"),
        last_name=raw.get("last_name"),
        patronymic=raw.get("patronymic"),
        phone=raw.get("phone"),
        photo_url=raw.get("photo_url"),
        _clear_patronymic="patronymic" in raw and raw["patronymic"] is None,
        _clear_phone="phone" in raw and raw["phone"] is None,
        _clear_photo="photo_url" in raw and raw["photo_url"] is None,
    )


def change_email(db: Session, user: User, payload: EmailChangeRequest) -> User:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный текущий пароль",
        )
    new_email = str(payload.new_email).strip().lower()
    if new_email == user.email:
        return user
    if get_user_by_email(db, new_email):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email уже занят",
        )
    return update_user_email(db, user, new_email)


def change_password(db: Session, user: User, payload: PasswordChangeRequest) -> None:
    if not verify_password(payload.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный текущий пароль",
        )
    update_user_password(db, user, get_password_hash(payload.new_password))


def login_user(db: Session, email: str, password: str) -> TokenResponse:
    email = email.strip().lower()
    user = get_user_by_email(db, email)
    if user is None or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is inactive",
        )

    return _build_token_response(user)
