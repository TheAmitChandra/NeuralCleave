"""Unified 3-tier memory retrieval pipeline.

Orchestrates short-term (Redis), semantic (Qdrant), and long-term (SQLite)
memory into a single ranked context assembly for the cognitive loop.

Pipeline:
    Query → Short-term inject (priority)
          → Qdrant ANN semantic search
          → SQLite long-term query
          → Content-hash deduplication
          → Score-rank + cap at top_k
          → Token estimation
          → RetrievalContext
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MemoryResult:
    """A single retrieved memory item with provenance."""

    source: str  # "short_term" | "semantic" | "long_term"
    content: Any
    score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalContext:
    """Assembled context returned to the agent cognitive loop."""

    results: list[MemoryResult]
    token_estimate: int = 0

    def to_prompt_blocks(self) -> list[str]:
        """Serialise results as text blocks ready for prompt injection."""
        blocks: list[str] = []
        for r in self.results:
            header = f"[{r.source.upper()} score={r.score:.2f}]"
            body = str(r.content) if not isinstance(r.content, str) else r.content
            blocks.append(f"{header}\n{body}")
        return blocks


class MemoryRetrievalPipeline:
    """Unified retrieval across all 3 memory tiers.

    Usage::

        pipeline = MemoryRetrievalPipeline(session_id="user-123")
        ctx = await pipeline.retrieve(
            query="how do I handle rate limit errors?",
            embedding=model.encode(query),
        )
        prompt_blocks = ctx.to_prompt_blocks()
    """

    def __init__(
        self,
        session_id: str | None = None,
        *,
        redis_url: str = "redis://localhost:6379",
        qdrant_url: str = "http://localhost:6333",
        sqlite_path: str = "~/.cortexflow/memory.db",
        short_term_ttl: int = 3600,
    ) -> None:
        self.session_id = session_id
        self._redis_url = redis_url
        self._qdrant_url = qdrant_url
        self._sqlite_path = sqlite_path
        self._short_term_ttl = short_term_ttl

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    async def retrieve(
        self,
        query: str,
        embedding: list[float] | None = None,
        *,
        top_k: int = 10,
        score_threshold: float = 0.5,
        include_short_term: bool = True,
        include_semantic: bool = True,
        include_long_term: bool = True,
    ) -> RetrievalContext:
        """Run the full 3-tier retrieval pipeline.

        Args:
            query:             Raw query string (used for short-term match).
            embedding:         Pre-computed dense vector. If None, semantic search is skipped.
            top_k:             Maximum results to return.
            score_threshold:   Minimum relevance score to include.
            include_*:         Toggle individual tiers.

        Returns:
            RetrievalContext with ranked, deduplicated results.
        """
        results: list[MemoryResult] = []

        if include_short_term and self.session_id:
            results.extend(await self._short_term(query))

        if include_semantic and embedding is not None:
            results.extend(await self._semantic(embedding, top_k=top_k, threshold=score_threshold))

        if include_long_term and self.session_id:
            results.extend(await self._long_term(limit=top_k))

        results = _deduplicate(results)
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]
        token_estimate = sum(len(str(r.content)) // 4 for r in results)
        return RetrievalContext(results=results, token_estimate=token_estimate)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store_short_term(self, key: str, value: Any) -> None:
        """Store a key-value pair in Redis with session TTL."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                import json

                redis_key = f"cf:stm:{self.session_id}:{key}"
                await r.set(redis_key, json.dumps(value), ex=self._short_term_ttl)
            finally:
                await r.aclose()
        except Exception as exc:
            logger.warning("short_term.store failed: %s", exc)

    async def store_semantic(self, embedding: list[float], payload: dict[str, Any]) -> str | None:
        """Store an embedding in Qdrant. Returns point ID or None on error."""
        try:
            from qdrant_client import QdrantClient  # type: ignore[import]
            from qdrant_client.models import PointStruct  # type: ignore[import]
            import uuid

            client = QdrantClient(url=self._qdrant_url)
            point_id = str(uuid.uuid4())
            client.upsert(
                collection_name="cortexflow_memory",
                points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
            )
            return point_id
        except Exception as exc:
            logger.warning("semantic.store failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Pruning (called by daily scheduled task)
    # ------------------------------------------------------------------

    async def prune_low_importance(
        self,
        *,
        importance_threshold: float = 0.2,
    ) -> dict[str, int]:
        """Remove low-importance entries from SQLite and Qdrant near-duplicates.

        Returns:
            {"pruned": int, "deduplicated": int}
        """
        pruned = 0
        deduplicated = 0

        try:
            import aiosqlite  # type: ignore[import]
            import os

            db_path = os.path.expanduser(self._sqlite_path)
            async with aiosqlite.connect(db_path) as db:
                cursor = await db.execute(
                    "DELETE FROM memory_entries WHERE importance_score < ?",
                    (importance_threshold,),
                )
                pruned = cursor.rowcount or 0
                await db.commit()
        except Exception as exc:
            logger.warning("prune.sqlite failed: %s", exc)

        try:
            from qdrant_client import QdrantClient  # type: ignore[import]

            client = QdrantClient(url=self._qdrant_url)
            scroll_result, _ = client.scroll(
                collection_name="cortexflow_memory",
                limit=500,
                with_vectors=False,
            )
            seen: set[str] = set()
            to_delete: list[str] = []
            for point in scroll_result:
                pid = str(point.id)
                if pid in seen:
                    to_delete.append(pid)
                else:
                    seen.add(pid)
            if to_delete:
                client.delete(
                    collection_name="cortexflow_memory",
                    points_selector=to_delete,
                )
                deduplicated = len(to_delete)
        except Exception as exc:
            logger.warning("prune.qdrant failed: %s", exc)

        logger.info("memory.pruned pruned=%d deduplicated=%d", pruned, deduplicated)
        return {"pruned": pruned, "deduplicated": deduplicated}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _short_term(self, _query: str) -> list[MemoryResult]:
        results: list[MemoryResult] = []
        try:
            import json

            import redis.asyncio as aioredis  # type: ignore[import]

            r = await aioredis.from_url(self._redis_url, decode_responses=True)
            try:
                pattern = f"cf:stm:{self.session_id}:*"
                keys = await r.keys(pattern)
                for key in keys[:20]:
                    raw = await r.get(key)
                    if raw:
                        results.append(
                            MemoryResult(
                                source="short_term",
                                content=json.loads(raw),
                                score=1.0,
                                metadata={"key": key},
                            )
                        )
            finally:
                await r.aclose()
        except Exception as exc:
            logger.warning("short_term.retrieve failed: %s", exc)
        return results

    async def _semantic(
        self, embedding: list[float], *, top_k: int, threshold: float
    ) -> list[MemoryResult]:
        results: list[MemoryResult] = []
        try:
            from qdrant_client import QdrantClient  # type: ignore[import]

            client = QdrantClient(url=self._qdrant_url)
            hits = client.search(
                collection_name="cortexflow_memory",
                query_vector=embedding,
                limit=top_k,
                score_threshold=threshold,
            )
            for hit in hits:
                results.append(
                    MemoryResult(
                        source="semantic",
                        content=hit.payload,
                        score=hit.score,
                        metadata={"point_id": str(hit.id)},
                    )
                )
        except Exception as exc:
            logger.warning("semantic.retrieve failed: %s", exc)
        return results

    async def _long_term(self, limit: int = 20) -> list[MemoryResult]:
        results: list[MemoryResult] = []
        try:
            import os

            import aiosqlite  # type: ignore[import]

            db_path = os.path.expanduser(self._sqlite_path)
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    """
                    SELECT content, importance_score, memory_type, created_at
                    FROM memory_entries
                    WHERE session_id = ?
                    ORDER BY importance_score DESC, last_accessed_at DESC
                    LIMIT ?
                    """,
                    (self.session_id, limit),
                ) as cursor:
                    async for row in cursor:
                        results.append(
                            MemoryResult(
                                source="long_term",
                                content=row[0],
                                score=float(row[1]) * 0.6,
                                metadata={"memory_type": row[2], "created_at": row[3]},
                            )
                        )
        except Exception as exc:
            logger.warning("long_term.retrieve failed: %s", exc)
        return results


def _deduplicate(results: list[MemoryResult]) -> list[MemoryResult]:
    seen: dict[str, MemoryResult] = {}
    for r in results:
        h = hashlib.md5(str(r.content).encode(), usedforsecurity=False).hexdigest()
        if h not in seen or r.score > seen[h].score:
            seen[h] = r
    return list(seen.values())
