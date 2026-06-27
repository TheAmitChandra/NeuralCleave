"""Short-term memory — Redis-backed ephemeral key-value store per session.

Entries expire automatically via Redis TTL.  Keys follow the namespace
convention used by the retrieval pipeline::

    cf:stm:{session_id}:{key}

Usage::

    stm = ShortTermMemory(redis_url="redis://localhost:6379")
    await stm.store("user-123", "last_topic", "Python async", ttl=3600)
    value = await stm.get("user-123", "last_topic")
    all_items = await stm.get_all("user-123")
    await stm.delete("user-123", "last_topic")
    await stm.clear_session("user-123")
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_KEY_PREFIX = "cf:stm"
_DEFAULT_TTL = 3600  # 1 hour


def _key(session_id: str, field: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}:{field}"


def _pattern(session_id: str) -> str:
    return f"{_KEY_PREFIX}:{session_id}:*"


class ShortTermMemory:
    """Redis-backed session memory with automatic TTL expiry.

    Args:
        redis_url: Redis connection URL. Default: ``redis://localhost:6379``.
        default_ttl: Seconds until a stored entry expires (default 3600).
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        default_ttl: int = _DEFAULT_TTL,
    ) -> None:
        self._redis_url = redis_url
        self._default_ttl = default_ttl

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def store(
        self,
        session_id: str,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> bool:
        """Serialise *value* as JSON and store it under *key* for *session_id*.

        Args:
            session_id: Session/user identifier.
            key:        Arbitrary field name within the session namespace.
            value:      JSON-serialisable value.
            ttl:        Expiry in seconds. Falls back to ``default_ttl``.

        Returns True on success, False if Redis is unavailable.
        """
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                await r.set(
                    _key(session_id, key),
                    json.dumps(value),
                    ex=ttl if ttl is not None else self._default_ttl,
                )
            finally:
                await r.aclose()
            logger.debug("stm.stored session=%s key=%s", session_id, key)
            return True
        except Exception as exc:
            logger.warning("stm.store failed session=%s key=%s: %s", session_id, key, exc)
            return False

    async def delete(self, session_id: str, key: str) -> bool:
        """Delete a single entry. Returns True if the key existed."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                removed = await r.delete(_key(session_id, key))
            finally:
                await r.aclose()
            return bool(removed)
        except Exception as exc:
            logger.warning("stm.delete failed session=%s key=%s: %s", session_id, key, exc)
            return False

    async def clear_session(self, session_id: str) -> int:
        """Delete all keys belonging to *session_id*. Returns count deleted."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                keys = await r.keys(_pattern(session_id))
                if keys:
                    removed = await r.delete(*keys)
                else:
                    removed = 0
            finally:
                await r.aclose()
            logger.debug("stm.clear_session session=%s removed=%d", session_id, removed)
            return removed
        except Exception as exc:
            logger.warning("stm.clear_session failed session=%s: %s", session_id, exc)
            return 0

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get(self, session_id: str, key: str) -> Any | None:
        """Retrieve a single entry by key. Returns None if missing or Redis is down."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                raw = await r.get(_key(session_id, key))
            finally:
                await r.aclose()
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("stm.get failed session=%s key=%s: %s", session_id, key, exc)
            return None

    async def get_all(self, session_id: str, limit: int = 50) -> dict[str, Any]:
        """Return all entries for a session as a ``{key: value}`` dict.

        Keys are stripped of the namespace prefix so callers get bare field names.
        At most *limit* entries are returned.
        """
        result: dict[str, Any] = {}
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                keys = await r.keys(_pattern(session_id))
                for redis_key in keys[:limit]:
                    raw = await r.get(redis_key)
                    if raw is not None:
                        bare_key = redis_key.removeprefix(f"{_KEY_PREFIX}:{session_id}:")
                        try:
                            result[bare_key] = json.loads(raw)
                        except json.JSONDecodeError:
                            result[bare_key] = raw
            finally:
                await r.aclose()
        except Exception as exc:
            logger.warning("stm.get_all failed session=%s: %s", session_id, exc)
        return result

    async def ttl(self, session_id: str, key: str) -> int | None:
        """Return remaining TTL in seconds for *key*, or None if not found."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                remaining = await r.ttl(_key(session_id, key))
            finally:
                await r.aclose()
            # Redis returns -2 for missing keys, -1 for no TTL set
            return remaining if remaining >= 0 else None
        except Exception as exc:
            logger.warning("stm.ttl failed session=%s key=%s: %s", session_id, key, exc)
            return None
