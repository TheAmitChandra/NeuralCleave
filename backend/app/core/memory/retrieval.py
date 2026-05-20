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

from app.core.memory.episodic import EpisodicMemory
from app.core.memory.short_term import ShortTermMemory


@dataclass
class MemoryResult:
    """A single retrieved memory item with provenance metadata."""

    source: str          # "short_term" | "episodic" | "long_term" | "graph"
    content: Any
    score: float = 1.0   # higher = more relevant
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
        agent_id: UUID,
        *,
        short_term_ttl: int = 3600,
        episodic_collection: str = "conversation_embeddings",
    ) -> None:
        self.agent_id = agent_id
        self._stm = ShortTermMemory(agent_id, ttl=short_term_ttl)
        self._episodic = EpisodicMemory(agent_id, collection=episodic_collection)

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
        extra_episodic_filter: dict[str, Any] | None = None,
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
            extra_episodic_filter: Additional metadata filters for Qdrant.

        Returns:
            RetrievalContext with ranked, deduplicated results.
        """
        results: list[MemoryResult] = []

        # 1. Short-term context (highest priority — always injected first)
        if include_short_term:
            stm_results = await self._retrieve_short_term(query)
            results.extend(stm_results)

        # 2. Episodic / semantic search
        if include_episodic and embedding is not None:
            episodic_results = await self._retrieve_episodic(
                embedding,
                top_k=top_k,
                score_threshold=score_threshold,
                extra_filter=extra_episodic_filter,
            )
            results.extend(episodic_results)

        # 3. Deduplication (content hash)
        results = self._deduplicate(results)

        # 4. Sort by score descending, cap at top_k
        results.sort(key=lambda r: r.score, reverse=True)
        results = results[:top_k]

        # 5. Rough token estimation (4 chars ≈ 1 token)
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
            The Qdrant point ID if stored, or None if a near-duplicate was found.
        """
        if deduplicate:
            duplicates = await self._episodic.find_duplicates(
                embedding, threshold=similarity_threshold
            )
            if duplicates:
                return None  # skip storage — nearly identical entry exists

        return await self._episodic.store(embedding=embedding, payload=payload)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

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
