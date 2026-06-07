"""FastAPI dependency — extract and verify JWT from Authorization header."""

import uuid

import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security.zero_trust import verify_access_token
from app.db.models.user import User
from app.db.postgres import get_db

logger = structlog.get_logger(__name__)
_bearer = HTTPBearer(auto_error=True)

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid or expired token",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Verify JWT and return the authenticated User."""
    try:
        user_id_str = verify_access_token(credentials.credentials)
        user_id = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        logger.warning("invalid_token_attempt")
        raise _UNAUTHORIZED

    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )  # noqa: E712
    user = result.scalar_one_or_none()
    if not user:
        raise _UNAUTHORIZED
    return user


def require_role(*roles: str):
    """Factory — returns a dependency that enforces one of the given roles."""

    async def _check(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{current_user.role}' is not permitted for this action",
            )
        return current_user

    return _check
