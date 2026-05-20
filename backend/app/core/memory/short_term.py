"""Short-term memory backed by Redis.

Stores active working context for a running agent session.
TTL-based expiration (default 1 hour). Keys are scoped per agent.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from app.db.redis import get_redis


_DEFAULT_TTL = 3600  # 1 hour


def _key(agent_id: UUID, namespace: str = "ctx") -> str:
    return f"stm:{agent_id}:{namespace}"


class ShortTermMemory:
    """Redis-backed working memory for a single agent session.

    All values are JSON-serialised. Each logical namespace is a Redis Hash
    so individual fields can be read/written without deserialising the whole object.
    """

    def __init__(self, agent_id: UUID, ttl: int = _DEFAULT_TTL) -> None:
        self.agent_id = agent_id
        self.ttl = ttl

    # ------------------------------------------------------------------
    # Context window helpers
    # ------------------------------------------------------------------

    async def set(self, key: str, value: Any, namespace: str = "ctx") -> None:
        """Store a single field in the agent's working context."""
        redis = await get_redis()
        hash_key = _key(self.agent_id, namespace)
        await redis.hset(hash_key, key, json.dumps(value, default=str))
        await redis.expire(hash_key, self.ttl)

    async def get(self, key: str, namespace: str = "ctx") -> Any | None:
        """Retrieve a single field from the agent's working context."""
        redis = await get_redis()
        raw = await redis.hget(_key(self.agent_id, namespace), key)
        if raw is None:
            return None
        return json.loads(raw)

    async def get_all(self, namespace: str = "ctx") -> dict[str, Any]:
        """Return the entire namespace as a Python dict."""
        redis = await get_redis()
        raw = await redis.hgetall(_key(self.agent_id, namespace))
        return {k.decode() if isinstance(k, bytes) else k: json.loads(v) for k, v in raw.items()}

    async def delete(self, key: str, namespace: str = "ctx") -> None:
        """Remove a single field."""
        redis = await get_redis()
        await redis.hdel(_key(self.agent_id, namespace), key)

    async def clear(self, namespace: str = "ctx") -> None:
        """Wipe the entire namespace for this agent."""
        redis = await get_redis()
        await redis.delete(_key(self.agent_id, namespace))

    # ------------------------------------------------------------------
    # Message history helpers (used by the cognitive loop)
    # ------------------------------------------------------------------

    async def append_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history list."""
        redis = await get_redis()
        list_key = _key(self.agent_id, "messages")
        entry = json.dumps({"role": role, "content": content, "ts": datetime.utcnow().isoformat()})
        await redis.rpush(list_key, entry)
        await redis.expire(list_key, self.ttl)

    async def get_messages(self, limit: int = 50) -> list[dict[str, str]]:
        """Return the most recent N messages (oldest first)."""
        redis = await get_redis()
        list_key = _key(self.agent_id, "messages")
        raw_items = await redis.lrange(list_key, -limit, -1)
        return [json.loads(item) for item in raw_items]

    async def clear_messages(self) -> None:
        """Wipe the message history."""
        redis = await get_redis()
        await redis.delete(_key(self.agent_id, "messages"))

    # ------------------------------------------------------------------
    # Token budget tracking
    # ------------------------------------------------------------------

    async def increment_tokens(self, count: int) -> int:
        """Increment the session token counter. Returns the new total."""
        redis = await get_redis()
        budget_key = _key(self.agent_id, "tokens")
        total = await redis.incrby(budget_key, count)
        await redis.expire(budget_key, self.ttl)
        return int(total)

    async def get_token_count(self) -> int:
        """Return total tokens consumed in this session."""
        redis = await get_redis()
        raw = await redis.get(_key(self.agent_id, "tokens"))
        return int(raw) if raw else 0

    # ------------------------------------------------------------------
    # TTL management
    # ------------------------------------------------------------------

    async def refresh_ttl(self) -> None:
        """Reset the TTL on all namespaces for this agent."""
        redis = await get_redis()
        for namespace in ("ctx", "messages", "tokens"):
            await redis.expire(_key(self.agent_id, namespace), self.ttl)

    async def ttl_remaining(self, namespace: str = "ctx") -> int:
        """Return seconds until expiry (-1 if no expiry, -2 if key missing)."""
        redis = await get_redis()
        return await redis.ttl(_key(self.agent_id, namespace))
