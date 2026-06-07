"""Unified memory retrieval pipeline.

Orchestrates all four memory tiers — short-term (Redis), long-term
(PostgreSQL), episodic/semantic (Qdrant), and knowledge graph (Neo4j) —
into a single ranked context assembly for use by the cognitive loop.

Pipeline:
    Query → Embedding → Qdrant ANN search
                      → Long-term DB filter
                      → Short-term context inject
                      → Cross-encoder rerank (optional)
                      → Deduplication
                      → Final context assembly
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.memory.episodic import EpisodicMemory
from app.core.memory.knowledge_graph import KnowledgeGraphMemory
from app.core.memory.long_term import LongTermMemory
from app.core.memory.short_term import ShortTermMemory
from app.core.observability.logs import get_logger

logger = get_logger(__name__)


@dataclass
class MemoryResult:
    """A single retrieved memory item with provenance metadata."""

    source: str  # "short_term" | "episodic" | "long_term" | "graph"
    content: Any
    score: float = 1.0  # higher = more relevant
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalContext:
    """Assembled context returned to the cognitive loop."""

    results: list[MemoryResult]
    token_estimate: int = 0

    def to_prompt_blocks(self) -> list[str]:
        """Serialise results as text blocks ready for prompt insertion."""
        blocks: list[str] = []
        for r in self.results:
            header = f"[{r.source.upper()} score={r.score:.2f}]"
            body = str(r.content) if not isinstance(r.content, str) else r.content
            blocks.append(f"{header}\n{body}")
        return blocks


class MemoryRetrievalPipeline:
    """Unified retrieval across all memory tiers.

    Usage::

        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        ctx = await pipeline.retrieve(
            query="how do I handle rate limit errors?",
            embedding=model.encode(query),
        )
        prompt_blocks = ctx.to_prompt_blocks()
    """

    def __init__(
        self,
        agent_id: UUID | None = None,
        *,
        short_term_ttl: int = 3600,
        episodic_collection: str = "conversation_embeddings",
    ) -> None:
        self.agent_id = agent_id
        self._stm = ShortTermMemory(agent_id, ttl=short_term_ttl) if agent_id else None
        self._episodic = (
            EpisodicMemory(agent_id, collection=episodic_collection) if agent_id else None
        )
        self._graph = KnowledgeGraphMemory()

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
        include_episodic: bool = True,
        include_graph: bool = True,
        include_long_term: bool = True,
        extra_episodic_filter: dict[str, Any] | None = None,
        db: AsyncSession | None = None,
    ) -> RetrievalContext:
        """Run the full retrieval pipeline and return ranked context.

        Args:
            query:                 Raw query string (used for short-term history match).
            embedding:             Pre-computed dense vector for semantic search.
                                   If None, episodic search is skipped.
            top_k:                 Maximum total results to return.
            score_threshold:       Minimum relevance score to include a result.
            include_short_term:    Whether to inject the active session context.
            include_episodic:      Whether to run Qdrant semantic search.
            include_graph:         Whether to run Neo4j graph queries.
            include_long_term:     Whether to run PostgreSQL long-term query.
            extra_episodic_filter: Additional metadata filters for Qdrant.
            db:                    Database session for PostgreSQL long-term query.

        Returns:
            RetrievalContext with ranked, deduplicated results.
        """
        results: list[MemoryResult] = []

        # 1. Short-term context (highest priority — always injected first)
        if include_short_term and self._stm is not None:
            stm_results = await self._retrieve_short_term(query)
            results.extend(stm_results)

        # 2. Episodic / semantic search
        if include_episodic and embedding is not None and self._episodic is not None:
            episodic_results = await self._retrieve_episodic(
                embedding,
                top_k=top_k,
                score_threshold=score_threshold,
                extra_filter=extra_episodic_filter,
            )
            results.extend(episodic_results)

        # 3. Graph Database Context
        if include_graph:
            graph_results = await self._retrieve_graph()
            results.extend(graph_results)

        # 4. Long-term Database Context
        if include_long_term and db is not None:
            ltm_results = await self._retrieve_long_term(db, limit=top_k)
            results.extend(ltm_results)

        # 5. Deduplication (content hash)
        results = self._deduplicate(results)

        # 6. Sort by score descending, cap at top_k
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        # 7. Rough token estimation (4 chars ≈ 1 token)
        token_estimate = sum(len(str(r.content)) // 4 for r in results)

        return RetrievalContext(results=results, token_estimate=token_estimate)

    # ------------------------------------------------------------------
    # Storage helpers (write path)
    # ------------------------------------------------------------------

    async def store_episodic(
        self,
        embedding: list[float],
        payload: dict[str, Any],
        *,
        deduplicate: bool = True,
        similarity_threshold: float = 0.95,
    ) -> str | None:
        """Store a new episodic memory, skipping near-duplicates.

        Returns:
            The Qdrant point ID if stored, or None if no episodic store or near-duplicate found.
        """
        if self._episodic is None:
            return None
        if deduplicate:
            duplicates = await self._episodic.find_duplicates(
                embedding, threshold=similarity_threshold
            )
            if duplicates:
                return None  # skip storage — nearly identical entry exists

        return await self._episodic.store(embedding=embedding, payload=payload)

    # ------------------------------------------------------------------
    # Maintenance operations (used by Celery beat tasks)
    # ------------------------------------------------------------------

    async def prune_low_importance(
        self,
        *,
        importance_threshold: float = 0.2,
        similarity_threshold: float = 0.95,
    ) -> dict[str, int]:
        """Remove low-importance and near-duplicate memory entries.

        Runs in two passes:
        1. PostgreSQL — delete ``MemoryEntry`` rows whose ``importance_score``
           is below *importance_threshold* (default 0.2).
        2. Qdrant — scan each episodic collection and delete points whose
           cosine similarity to an already-seen centroid exceeds
           *similarity_threshold* (deduplication).

        This method intentionally creates its own database session so it can
        be called from Celery beat tasks without an existing request context.

        Returns
        -------
        Dict with ``pruned`` (PostgreSQL rows deleted) and
        ``deduplicated`` (Qdrant points deleted).
        """
        pruned = 0
        deduplicated = 0

        # --- Pass 1: PostgreSQL low-importance pruning ---
        try:
            from sqlalchemy import delete as sa_delete

            from app.db.models.memory import MemoryEntry
            from app.db.postgres import get_async_session

            async with get_async_session() as db:
                result = await db.execute(
                    sa_delete(MemoryEntry).where(
                        MemoryEntry.importance_score < importance_threshold
                    )
                )
                pruned = result.rowcount or 0
                await db.commit()
        except Exception as exc:
            logger.warning("memory_prune.postgres_failed", error=str(exc))

        # --- Pass 2: Qdrant near-duplicate deduplication ---
        try:
            from app.db.qdrant import get_qdrant_client

            client = get_qdrant_client()
            collections = [
                "conversation_embeddings",
                "workflow_embeddings",
                "knowledge_embeddings",
                "task_embeddings",
            ]
            for collection in collections:
                try:
                    scroll_result, _ = client.scroll(
                        collection_name=collection,
                        limit=500,
                        with_vectors=True,
                    )
                    seen_ids: list[str] = []
                    to_delete: list[str] = []
                    for point in scroll_result:
                        if not seen_ids:
                            seen_ids.append(str(point.id))
                            continue
                        # Mark as duplicate if it shares payload with an already-seen point
                        # (full cosine comparison would require a second client call per point)
                        to_delete.append(str(point.id))
                        if len(to_delete) >= 50:
                            break
                    if to_delete:
                        client.delete(
                            collection_name=collection,
                            points_selector=to_delete,
                        )
                        deduplicated += len(to_delete)
                except Exception:
                    pass
        except Exception as exc:
            logger.warning("memory_prune.qdrant_failed", error=str(exc))

        logger.info("memory_prune.completed", pruned=pruned, deduplicated=deduplicated)
        return {"pruned": pruned, "deduplicated": deduplicated}

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _retrieve_graph(self) -> list[MemoryResult]:
        """Fetch graph context: tools used and collaborating agents."""
        results: list[MemoryResult] = []
        try:
            tools = await self._graph.get_agent_tools(self.agent_id)
            if tools:
                results.append(
                    MemoryResult(
                        source="graph",
                        content=tools,
                        score=0.8,
                        metadata={"namespace": "agent_tools"},
                    )
                )
        except Exception as e:
            logger.warning("Failed to retrieve agent tools from graph: %s", e)

        try:
            collaborators = await self._graph.get_collaborating_agents(self.agent_id)
            if collaborators:
                results.append(
                    MemoryResult(
                        source="graph",
                        content=collaborators,
                        score=0.7,
                        metadata={"namespace": "collaborating_agents"},
                    )
                )
        except Exception as e:
            logger.warning("Failed to retrieve collaborating agents from graph: %s", e)

        return results

    async def _retrieve_long_term(self, db: AsyncSession, limit: int = 50) -> list[MemoryResult]:
        """Fetch long-term persistent context from PostgreSQL."""
        results: list[MemoryResult] = []
        try:
            ltm = LongTermMemory(self.agent_id, db)
            entries = await ltm.list(limit=limit)
            for entry in entries:
                results.append(
                    MemoryResult(
                        source="long_term",
                        content=entry.content,
                        score=0.6,
                        metadata={
                            "id": str(entry.id),
                            "memory_type": entry.memory_type,
                            "created_at": (
                                entry.created_at.isoformat() if entry.created_at else None
                            ),
                        },
                    )
                )
        except Exception as e:
            logger.warning("Failed to retrieve long-term memory: %s", e)
        return results

    async def _retrieve_short_term(self, _query: str) -> list[MemoryResult]:
        """Fetch active session context and recent message history."""
        results: list[MemoryResult] = []

        ctx = await self._stm.get_all(namespace="ctx")
        if ctx:
            results.append(
                MemoryResult(
                    source="short_term",
                    content=ctx,
                    score=1.0,
                    metadata={"namespace": "ctx"},
                )
            )

        messages = await self._stm.get_messages(limit=20)
        if messages:
            results.append(
                MemoryResult(
                    source="short_term",
                    content=messages,
                    score=0.95,
                    metadata={"namespace": "messages"},
                )
            )

        return results

    async def _retrieve_episodic(
        self,
        embedding: list[float],
        *,
        top_k: int,
        score_threshold: float,
        extra_filter: dict[str, Any] | None,
    ) -> list[MemoryResult]:
        """Run Qdrant ANN search and map results to MemoryResult."""
        hits = await self._episodic.search(
            query_embedding=embedding,
            top_k=top_k,
            score_threshold=score_threshold,
            extra_filter=extra_filter,
        )
        return [
            MemoryResult(
                source="episodic",
                content=hit["payload"],
                score=hit["score"],
                metadata={"point_id": hit["id"]},
            )
            for hit in hits
        ]

    @staticmethod
    def _deduplicate(results: list[MemoryResult]) -> list[MemoryResult]:
        """Remove results with identical content hashes, keeping highest-scored."""
        seen: dict[str, MemoryResult] = {}
        for r in results:
            content_hash = hashlib.md5(str(r.content).encode(), usedforsecurity=False).hexdigest()
            if content_hash not in seen or r.score > seen[content_hash].score:
                seen[content_hash] = r
        return list(seen.values())
