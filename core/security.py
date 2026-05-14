import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from core.config import settings

_BCRYPT_LEGACY_MAX_BYTES = 72


class TokenValidationError(Exception):
    pass


def verify_password(plain_password: str, hashed_password: str) -> bool:
    h = hashed_password.encode("utf-8")
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    try:
        if bcrypt.checkpw(digest, h):
            return True
    except ValueError:
        return False

    raw = plain_password.encode("utf-8")
    if len(raw) > _BCRYPT_LEGACY_MAX_BYTES:
        return False
    try:
        return bcrypt.checkpw(raw, h)
    except ValueError:
        return False


def get_password_hash(password: str) -> str:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return bcrypt.hashpw(digest, bcrypt.gensalt()).decode()


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "exp": int(expire.timestamp()),
        "iat": int(datetime.now(timezone.utc).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
        )
    except JWTError as exc:
        raise TokenValidationError("Invalid or expired token") from exc


def access_token_ttl_seconds() -> int:
    return settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
