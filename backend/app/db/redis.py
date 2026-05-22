"""Redis async connection using redis-py."""

import structlog
from redis.asyncio import ConnectionPool, Redis

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

_pool: ConnectionPool | None = None
_client: Redis | None = None


async def init_redis() -> None:
    global _pool, _client
    _pool = ConnectionPool.from_url(
        settings.REDIS_URL,
        password=settings.REDIS_PASSWORD or None,
        max_connections=50,
        decode_responses=True,
    )
    _client = Redis(connection_pool=_pool)
    await _client.ping()
    logger.info("redis_connected")


async def close_redis() -> None:
    global _client, _pool
    if _client:
        await _client.aclose()
    if _pool:
        await _pool.aclose()
    logger.info("redis_disconnected")


async def check_redis_health() -> bool:
    try:
        if _client:
            await _client.ping()
            return True
        return False
    except Exception:
        return False


async def get_redis() -> Redis:
    """Return the shared Redis client (must call init_redis first)."""
    if _client is None:
        raise RuntimeError("Redis not initialised — call init_redis() first")
    return _client
