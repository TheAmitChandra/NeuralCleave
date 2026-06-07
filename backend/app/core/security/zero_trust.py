"""JWT authentication utilities — token creation, verification, password hashing."""

from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt as _bcrypt
from jose import JWTError, jwt

from app.config import get_settings

settings = get_settings()


# ── Password ──────────────────────────────────────────────────────────────────


def hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── Token creation ────────────────────────────────────────────────────────────


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    expire = datetime.now(UTC) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "access",
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(UTC) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(UTC),
        "type": "refresh",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


# ── Token verification ────────────────────────────────────────────────────────


def decode_token(token: str) -> dict[str, Any]:
    """Decode and verify a JWT. Raises JWTError on failure."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def verify_access_token(token: str) -> str:
    """Return subject (user_id) if token is a valid access token."""
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise JWTError("Not an access token")
    sub: str | None = payload.get("sub")
    if not sub:
        raise JWTError("Missing subject")
    return sub


def verify_refresh_token(token: str) -> str:
    """Return subject (user_id) if token is a valid refresh token."""
    payload = decode_token(token)
    if payload.get("type") != "refresh":
        raise JWTError("Not a refresh token")
    sub: str | None = payload.get("sub")
    if not sub:
        raise JWTError("Missing subject")
    return sub
