import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.user import User

_STATIONARY_COORD_EPS = Decimal("0.000045")
_SKIP_IF_UNCHANGED_SECONDS = 12


def get_user_by_id(db: Session, user_id: uuid.UUID) -> User | None:
    return db.get(User, user_id)


def get_user_by_email(db: Session, email: str) -> User | None:
    query = select(User).where(User.email == email)
    return db.execute(query).scalar_one_or_none()


def get_user_by_phone(db: Session, phone: str) -> User | None:
    query = select(User).where(User.phone == phone)
    return db.execute(query).scalar_one_or_none()


def create_user(
    db: Session,
    *,
    email: str,
    password_hash: str,
    last_name: str,
    first_name: str,
    patronymic: str | None,
    role: str,
    phone: str | None = None,
    photo_url: str | None = None,
) -> User:
    user = User(
        email=email,
        password_hash=password_hash,
        last_name=last_name,
        first_name=first_name,
        patronymic=patronymic,
        role=role,
        phone=phone,
        photo_url=photo_url,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_user_profile(
    db: Session,
    user: User,
    *,
    first_name: str | None,
    last_name: str | None,
    patronymic: str | None,
    phone: str | None,
    photo_url: str | None,
    _clear_phone: bool,
    _clear_photo: bool,
    _clear_patronymic: bool,
) -> User:
    if first_name is not None:
        user.first_name = first_name.strip()
    if last_name is not None:
        user.last_name = last_name.strip()
    if _clear_patronymic:
        user.patronymic = None
    elif patronymic is not None:
        user.patronymic = patronymic.strip() or None
    if _clear_phone:
        user.phone = None
    elif phone is not None:
        user.phone = phone
    if _clear_photo:
        user.photo_url = None
    elif photo_url is not None:
        user.photo_url = photo_url.strip() or None
    db.commit()
    db.refresh(user)
    return user


def update_user_email(db: Session, user: User, new_email: str) -> User:
    user.email = new_email
    db.commit()
    db.refresh(user)
    return user


def update_user_password(db: Session, user: User, new_hash: str) -> User:
    user.password_hash = new_hash
    db.commit()
    db.refresh(user)
    return user


def update_user_location(
    db: Session,
    user_id: uuid.UUID,
    *,
    lat: Decimal,
    lng: Decimal,
    coalesce_stationary_recent: bool = False,
) -> User | None:
    user = db.get(User, user_id)
    if user is None:
        return None

    now = datetime.now(timezone.utc)

    if coalesce_stationary_recent and user.lat is not None and user.lng is not None:
        if user.location_updated_at is not None:
            last_at = user.location_updated_at
            if last_at.tzinfo is None:
                last_at = last_at.replace(tzinfo=timezone.utc)
            else:
                last_at = last_at.astimezone(timezone.utc)
            elapsed = (now - last_at).total_seconds()
            if elapsed < _SKIP_IF_UNCHANGED_SECONDS:
                if (
                    abs(lat - user.lat) <= _STATIONARY_COORD_EPS
                    and abs(lng - user.lng) <= _STATIONARY_COORD_EPS
                ):
                    return user

    user.lat = lat
    user.lng = lng
    user.location_updated_at = now
    db.commit()
    db.refresh(user)
    return user
