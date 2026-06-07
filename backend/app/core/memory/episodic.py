"""Episodic / semantic memory backed by Qdrant.

Stores and retrieves dense vector embeddings using sentence-transformers.
Supports semantic nearest-neighbour search with optional metadata filtering.
"""

from __future__ import annotations

import uuid
from typing import Any
from uuid import UUID

from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.db.qdrant import get_qdrant_client

# Default collection used for episodic memory
_COLLECTION = "conversation_embeddings"

# Embedding dimension produced by all-MiniLM-L6-v2
_VECTOR_DIM = 384


class EpisodicMemory:
    """Qdrant-backed semantic memory — store and search embeddings.

    Embeddings are expected to be pre-computed (e.g. by
    ``sentence_transformers.SentenceTransformer("all-MiniLM-L6-v2")``)
    and passed in as plain Python lists.  This class is deliberately
    decoupled from the embedding model so the caller can swap encoders.
    """

    def __init__(self, agent_id: UUID, collection: str = _COLLECTION) -> None:
        self.agent_id = str(agent_id)
        self.collection = collection

    # ------------------------------------------------------------------
    # Upsert
    # ------------------------------------------------------------------

    async def store(
        self,
        embedding: list[float],
        payload: dict[str, Any],
        point_id: str | None = None,
    ) -> str:
        """Insert or overwrite a single vector point.

        Args:
            embedding: Dense vector (length must match collection dimension).
            payload:   Arbitrary metadata stored alongside the vector.
            point_id:  Deterministic UUID string for idempotent upserts.

        Returns:
            The Qdrant point ID used.
        """
        client = await get_qdrant_client()
        if point_id is None:
            point_id = str(uuid.uuid4())

        full_payload = {
            **payload,
            "agent_id": self.agent_id,
        }

        await client.upsert(
            collection_name=self.collection,
            points=[PointStruct(id=point_id, vector=embedding, payload=full_payload)],
        )
        return point_id

    async def store_batch(
        self,
        items: list[tuple[list[float], dict[str, Any]]],
    ) -> list[str]:
        """Batch upsert for efficiency when storing many entries at once.

        Args:
            items: List of (embedding, payload) tuples.

        Returns:
            List of point IDs in the same order.
        """
        client = await get_qdrant_client()
        points = []
        ids: list[str] = []
        for embedding, payload in items:
            pid = str(uuid.uuid4())
            ids.append(pid)
            points.append(
                PointStruct(
                    id=pid,
                    vector=embedding,
                    payload={**payload, "agent_id": self.agent_id},
                )
            )
        await client.upsert(collection_name=self.collection, points=points)
        return ids

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 10,
        score_threshold: float = 0.5,
        extra_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic nearest-neighbour search scoped to this agent.

        Args:
            query_embedding:  Query vector.
            top_k:            Maximum results to return.
            score_threshold:  Minimum cosine similarity to include.
            extra_filter:     Optional additional metadata filter dict
                              (``{field: value}`` pairs ANDed with agent filter).

        Returns:
            List of dicts with keys: ``id``, ``score``, ``payload``.
        """
        client = await get_qdrant_client()

        conditions: list[FieldCondition] = [
            FieldCondition(key="agent_id", match=MatchValue(value=self.agent_id))
        ]
        if extra_filter:
            for field, value in extra_filter.items():
                conditions.append(FieldCondition(key=field, match=MatchValue(value=value)))

        hits = await client.search(
            collection_name=self.collection,
            query_vector=query_embedding,
            limit=top_k,
            score_threshold=score_threshold,
            query_filter=Filter(must=conditions),
            with_payload=True,
        )
        return [{"id": str(h.id), "score": h.score, "payload": h.payload} for h in hits]

    # ------------------------------------------------------------------
    # Retrieval by ID
    # ------------------------------------------------------------------

    async def get(self, point_id: str) -> dict[str, Any] | None:
        """Fetch a single point by its Qdrant ID."""
        client = await get_qdrant_client()
        results = await client.retrieve(
            collection_name=self.collection,
            ids=[point_id],
            with_payload=True,
            with_vectors=False,
        )
        if not results:
            return None
        point = results[0]
        return {"id": str(point.id), "payload": point.payload}

    # ------------------------------------------------------------------
    # Deletion
    # ------------------------------------------------------------------

    async def delete(self, point_id: str) -> None:
        """Remove a single point by ID."""
        client = await get_qdrant_client()
        await client.delete(
            collection_name=self.collection,
            points_selector=[point_id],
        )

    async def delete_agent_memory(self) -> None:
        """Delete ALL vectors belonging to this agent (e.g. on agent teardown)."""
        from qdrant_client.http.models import FilterSelector

        client = await get_qdrant_client()
        await client.delete(
            collection_name=self.collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must=[FieldCondition(key="agent_id", match=MatchValue(value=self.agent_id))]
                )
            ),
        )

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    async def find_duplicates(
        self,
        embedding: list[float],
        threshold: float = 0.95,
    ) -> list[dict[str, Any]]:
        """Return any existing vectors with similarity >= threshold.

        Used before storing to prevent near-duplicate entries.
        """
        return await self.search(
            query_embedding=embedding,
            top_k=5,
            score_threshold=threshold,
        )
