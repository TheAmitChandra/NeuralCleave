"""Unified 3-tier memory retrieval pipeline.

Orchestrates short-term (Redis), semantic (Qdrant), and long-term (SQLite)
memory into a single ranked context assembly for the cognitive loop.

Both Redis and Qdrant are optional at runtime. When unavailable the pipeline
falls back to in-process storage so the desktop app works with zero external
services installed.

Pipeline:
    Query → Short-term inject (priority)
          → Qdrant ANN semantic search  (in-memory cosine fallback)
          → SQLite long-term query
          → Content-hash deduplication
          → Score-rank + cap at top_k
          → Token estimation
          → RetrievalContext
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from neuralcleave.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)

_QDRANT_COLLECTION = "NeuralCleave_memory"

# Seconds to wait before re-probing Qdrant after a failed attempt.
_QDRANT_RECHECK_INTERVAL = 30.0


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


# ---------------------------------------------------------------------------
# In-process vector store (Qdrant fallback)
# ---------------------------------------------------------------------------

class _InMemoryVectorStore:
    """Cosine-similarity search over an in-process list of vectors.

    Used when Qdrant is unavailable so the desktop app retains semantic
    memory without any external services. All callers are async and run
    on the event loop; the list is touched only from that loop, so no
    threading lock is required.
    """

    def __init__(self) -> None:
        self._points: list[dict[str, Any]] = []

    def upsert(self, point_id: str, vector: list[float], payload: dict[str, Any]) -> None:
        self._points = [p for p in self._points if p["id"] != point_id]
        self._points.append({"id": point_id, "vector": vector, "payload": payload})

    def search(
        self,
        query: list[float],
        top_k: int,
        threshold: float,
    ) -> list[tuple[str, dict[str, Any], float]]:
        if not self._points or not query:
            return []
        q_norm = math.sqrt(sum(x * x for x in query))
        if q_norm == 0.0:
            return []
        results: list[tuple[str, dict[str, Any], float]] = []
        for point in self._points:
            v = point["vector"]
            v_norm = math.sqrt(sum(x * x for x in v))
            if v_norm == 0.0:
                continue
            dot = sum(a * b for a, b in zip(query, v))
            score = dot / (q_norm * v_norm)
            if score >= threshold:
                results.append((point["id"], point["payload"], score))
        results.sort(key=lambda x: x[2], reverse=True)
        return results[:top_k]

    def clear(self) -> None:
        self._points.clear()

    def __len__(self) -> int:
        return len(self._points)


# Module-level singleton: shared across all MemoryRetrievalPipeline instances.
_MEM_VECTOR_STORE = _InMemoryVectorStore()


# ---------------------------------------------------------------------------
# MemoryRetrievalPipeline
# ---------------------------------------------------------------------------

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
        sqlite_path: str = "~/.neuralcleave/memory.db",
        short_term_ttl: int = 3600,
    ) -> None:
        self.session_id = session_id
        self._redis_url = redis_url
        self._qdrant_url = qdrant_url
        self._sqlite_path = sqlite_path
        self._short_term_ttl = short_term_ttl
        # Shared short-term backend (Redis with in-memory fallback).
        self._stm = ShortTermMemory(redis_url=redis_url, default_ttl=short_term_ttl)
        # Qdrant probe cache: True = available, False = unavailable, None = unchecked.
        self._qdrant_ok: bool | None = None
        self._qdrant_check_at: float = 0.0

    # ------------------------------------------------------------------
    # Qdrant availability probe (cached, 1 s timeout)
    # ------------------------------------------------------------------

    async def _probe_qdrant(self) -> bool:
        """Return True if Qdrant is reachable; cache result to avoid per-call checks."""
        now = time.monotonic()
        if self._qdrant_ok is True:
            return True
        if self._qdrant_ok is False and now - self._qdrant_check_at < _QDRANT_RECHECK_INTERVAL:
            return False
        try:
            from qdrant_client import AsyncQdrantClient  # type: ignore[import]

            client = AsyncQdrantClient(url=self._qdrant_url)
            await asyncio.wait_for(client.get_collections(), timeout=1.0)
            if self._qdrant_ok is not True:
                logger.info(
                    "retrieval: Qdrant available at %s — using Qdrant backend", self._qdrant_url
                )
            self._qdrant_ok = True
        except Exception:
            if self._qdrant_ok is not False:
                logger.info(
                    "retrieval: Qdrant unavailable at %s — using in-memory vector store",
                    self._qdrant_url,
                )
            self._qdrant_ok = False
            self._qdrant_check_at = now
        return bool(self._qdrant_ok)

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
        session_id: str | None = None,
    ) -> RetrievalContext:
        """Run the full 3-tier retrieval pipeline.

        Args:
            query:             Raw query string (used for short-term match).
            embedding:         Pre-computed dense vector. If None, semantic search is skipped.
            top_k:             Maximum results to return.
            score_threshold:   Minimum relevance score to include.
            include_*:         Toggle individual tiers.
            session_id:        Per-call override for the session ID. Takes precedence over
                               self.session_id, allowing callers to supply the current
                               session without reconstructing the pipeline per message.

        Returns:
            RetrievalContext with ranked, deduplicated results.
        """
        eff_sid = session_id if session_id is not None else self.session_id
        results: list[MemoryResult] = []

        if include_short_term and eff_sid:
            results.extend(await self._short_term(query, session_id=eff_sid))

        if include_semantic and embedding is not None:
            results.extend(await self._semantic(embedding, top_k=top_k, threshold=score_threshold))

        if include_long_term:
            # Cross-session retrieval is intentional: NeuralCleave is a single-user
            # assistant, so all stored exchanges (regardless of which channel UUID
            # wrote them) should be visible in the context window.
            results.extend(await self._long_term(limit=top_k, query=query, session_id=None))

        results = _deduplicate(results)
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]
        token_estimate = sum(len(str(r.content)) // 4 for r in results)
        return RetrievalContext(results=results, token_estimate=token_estimate)

    # ------------------------------------------------------------------
    # Store
    # ------------------------------------------------------------------

    async def store_short_term(self, key: str, value: Any, session_id: str | None = None) -> None:
        """Store a key-value pair in short-term memory (Redis, with in-memory fallback).

        ``session_id`` overrides ``self.session_id`` for this call so the
        pipeline can supply the current session without a per-session pipeline.
        No-op (with a debug log) when no session_id is resolvable.
        """
        eff_sid = session_id if session_id is not None else self.session_id
        if eff_sid is None:
            logger.debug("store_short_term: skipped — no session_id available")
            return
        await self._stm.store(eff_sid, key, value)

    async def store_semantic(self, embedding: list[float], payload: dict[str, Any]) -> str | None:
        """Store an embedding in Qdrant (or in-memory fallback). Returns point ID."""
        point_id = str(uuid.uuid4())
        if await self._probe_qdrant():
            try:
                from qdrant_client import AsyncQdrantClient  # type: ignore[import]
                from qdrant_client.models import (  # type: ignore[import]
                    Distance,
                    PointStruct,
                    VectorParams,
                )

                client = AsyncQdrantClient(url=self._qdrant_url)
                try:
                    try:
                        await client.upsert(
                            collection_name=_QDRANT_COLLECTION,
                            points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
                        )
                    except Exception as e:
                        # Collection may not exist yet — create it with the correct dimensions.
                        if "not found" in str(e).lower() or "doesn't exist" in str(e).lower():
                            await client.create_collection(
                                _QDRANT_COLLECTION,
                                vectors_config=VectorParams(
                                    size=len(embedding), distance=Distance.COSINE
                                ),
                            )
                            await client.upsert(
                                collection_name=_QDRANT_COLLECTION,
                                points=[PointStruct(id=point_id, vector=embedding, payload=payload)],
                            )
                        else:
                            raise
                    logger.debug("semantic.stored (qdrant) point_id=%s", point_id)
                    return point_id
                finally:
                    await client.close()
            except Exception as exc:
                logger.warning("semantic.store qdrant failed, falling back to memory: %s", exc)
                self._qdrant_ok = None  # force re-probe next call

        _MEM_VECTOR_STORE.upsert(point_id, embedding, payload)
        logger.debug("semantic.stored (memory) point_id=%s", point_id)
        return point_id

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
            import os

            import aiosqlite  # type: ignore[import]

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
            from qdrant_client import AsyncQdrantClient  # type: ignore[import]
            from qdrant_client.models import (  # type: ignore[import]
                FieldCondition,
                Filter,
                Range,
            )

            client = AsyncQdrantClient(url=self._qdrant_url)
            try:
                # Delete points whose stored importance_score falls below the threshold.
                low_importance_filter = Filter(
                    must=[
                        FieldCondition(
                            key="importance_score",
                            range=Range(lt=importance_threshold),
                        )
                    ]
                )
                delete_result = await client.delete(
                    collection_name=_QDRANT_COLLECTION,
                    points_selector=low_importance_filter,
                )
                pruned_qdrant = getattr(delete_result, "operation_id", 0) or 0
                deduplicated += int(pruned_qdrant)

                # Secondary pass: remove exact-ID duplicates (defensive dedup).
                scroll_result, _ = await client.scroll(
                    collection_name=_QDRANT_COLLECTION,
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
                    await client.delete(
                        collection_name=_QDRANT_COLLECTION,
                        points_selector=to_delete,
                    )
                    deduplicated += len(to_delete)
            finally:
                await client.close()
        except Exception as exc:
            logger.warning("prune.qdrant failed: %s", exc)

        logger.info("memory.pruned pruned=%d deduplicated=%d", pruned, deduplicated)
        return {"pruned": pruned, "deduplicated": deduplicated}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _short_term(self, _query: str, session_id: str | None = None) -> list[MemoryResult]:
        eff_sid = session_id if session_id is not None else self.session_id
        if eff_sid is None:
            return []
        entries = await self._stm.get_all(eff_sid, limit=20)
        return [
            MemoryResult(
                source="short_term",
                content=value,
                score=1.0,
                metadata={"key": key},
            )
            for key, value in entries.items()
        ]

    async def _semantic(
        self, embedding: list[float], *, top_k: int, threshold: float
    ) -> list[MemoryResult]:
        if await self._probe_qdrant():
            try:
                from qdrant_client import AsyncQdrantClient  # type: ignore[import]

                client = AsyncQdrantClient(url=self._qdrant_url)
                hits = await client.search(
                    collection_name=_QDRANT_COLLECTION,
                    query_vector=embedding,
                    limit=top_k,
                    score_threshold=threshold,
                )
                logger.debug("semantic.retrieved (qdrant) hits=%d", len(hits))
                return [
                    MemoryResult(
                        source="semantic",
                        content=hit.payload,
                        score=hit.score,
                        metadata={"point_id": str(hit.id)},
                    )
                    for hit in hits
                ]
            except Exception as exc:
                logger.warning("semantic.retrieve qdrant failed, falling back to memory: %s", exc)
                self._qdrant_ok = None

        hits_mem = _MEM_VECTOR_STORE.search(embedding, top_k, threshold)
        logger.debug("semantic.retrieved (memory) hits=%d", len(hits_mem))
        return [
            MemoryResult(
                source="semantic",
                content=payload,
                score=score,
                metadata={"point_id": point_id, "fallback": True},
            )
            for point_id, payload, score in hits_mem
        ]

    async def _long_term(self, limit: int = 20, query: str = "", session_id: str | None = None) -> list[MemoryResult]:
        """Fetch long-term entries ranked by importance, optionally filtered by query text.

        session_id=None → cross-session (no filter). retrieve() deliberately passes
        None here so all channel sessions share one memory pool for this single-user
        assistant. Pass an explicit session_id to scope results to one session.
        """
        results: list[MemoryResult] = []
        try:
            import os

            import aiosqlite  # type: ignore[import]

            db_path = os.path.expanduser(self._sqlite_path)
            conditions: list[str] = []
            params: list[Any] = []

            if session_id is not None:
                conditions.append("session_id = ?")
                params.append(session_id)

            if query:
                conditions.append("content LIKE ?")
                params.append(f"%{query}%")

            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            params.append(limit)

            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    f"""
                    SELECT content, importance_score, memory_type, created_at
                    FROM memory_entries
                    {where}
                    ORDER BY importance_score DESC, last_accessed_at DESC
                    LIMIT ?
                    """,  # noqa: S608
                    tuple(params),
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
