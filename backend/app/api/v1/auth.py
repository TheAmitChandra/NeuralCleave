"""Auth API endpoints — login, refresh, logout, register, me."""

import uuid
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.core.security.permission_engine import get_current_user
from app.core.security.zero_trust import (
    create_access_token,
    create_refresh_token,
    hash_password,
    verify_password,
    verify_refresh_token,
)
from app.config import get_settings
from app.db.models.user import User
from app.db.postgres import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, TokenResponse, UserCreate, UserResponse

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/auth")
settings = get_settings()

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid email or password",
    headers={"WWW-Authenticate": "Bearer"},
)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(body: UserCreate, db: AsyncSession = Depends(get_db)) -> User:
    """Register a new user account."""
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
        role="developer",
    )
    db.add(user)
    await db.flush()
    logger.info("user_registered", user_id=str(user.id), email=user.email)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Authenticate and return access + refresh tokens."""
    result = await db.execute(select(User).where(User.email == body.email, User.is_active == True))  # noqa: E712
    user = result.scalar_one_or_none()

    if not user or not verify_password(body.password, user.hashed_password):
        logger.warning("failed_login_attempt", email=body.email, ip=request.client.host if request.client else None)
        raise _INVALID_CREDENTIALS

    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "tenant_id": user.tenant_id or "default"},
    )
    refresh_token = create_refresh_token(subject=str(user.id))

    logger.info("user_login", user_id=str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> dict:
    """Exchange a valid refresh token for a new token pair."""
    try:
        user_id_str = verify_refresh_token(body.refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token"
        )

    result = await db.execute(select(User).where(User.id == uuid.UUID(user_id_str), User.is_active == True))  # noqa: E712
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    access_token = create_access_token(
        subject=str(user.id),
        extra_claims={"role": user.role, "tenant_id": user.tenant_id or "default"},
    )
    new_refresh_token = create_refresh_token(subject=str(user.id))
    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response, response_model=None)
async def logout(current_user: User = Depends(get_current_user)) -> None:
    """Logout — client should discard tokens. Server-side blacklist via Redis is Phase 3."""
    logger.info("user_logout", user_id=str(current_user.id))


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)) -> User:
    """Return the currently authenticated user's profile."""
    return current_user
