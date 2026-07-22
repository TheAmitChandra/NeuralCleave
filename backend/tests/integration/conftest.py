"""
Integration test fixtures for NeuralCleave.

Strategy:
  - Sync session-scoped fixture creates all tables once using asyncio.run().
  - Each test gets an async DB session backed by a SAVEPOINT (rolled back after).
  - httpx.AsyncClient hits the real FastAPI ASGI app (not a mock server).
  - No external services mocked — requires a real PostgreSQL instance.

Prerequisites (set via environment variables or .env):
  DATABASE_URL=postgresql+asyncpg://neuralcleave:neuralcleave@localhost:5432/NeuralCleave_test
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db.postgres import Base, get_db
from app.main import app

_DB_URL: str = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://neuralcleave:neuralcleave@localhost:5432/NeuralCleave_test",
)

# ---------------------------------------------------------------------------
# Session-scoped synchronous fixture — create/drop schema once per run
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _setup_database() -> None:
    """Create all ORM tables before the integration suite runs, drop after."""

    async def _create() -> None:
        eng = create_async_engine(_DB_URL, echo=False)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        await eng.dispose()

    async def _drop() -> None:
        eng = create_async_engine(_DB_URL, echo=False)
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await eng.dispose()

    asyncio.run(_create())
    yield
    asyncio.run(_drop())


# ---------------------------------------------------------------------------
# Per-test transactional session (rolled back after each test)
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:  # noqa: PT004
    """
    Yield an async session inside a savepoint.
    The outer transaction is rolled back after each test — no data persists.
    """
    eng = create_async_engine(_DB_URL, echo=False)
    async with eng.connect() as conn:
        await conn.begin()
        factory = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        async with factory() as session:
            yield session
        await conn.rollback()
    await eng.dispose()


# ---------------------------------------------------------------------------
# httpx AsyncClient with get_db overridden
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient bound to the FastAPI ASGI app, using the test DB session."""

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
