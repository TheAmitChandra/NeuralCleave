"""Qdrant vector database client."""

import structlog
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams

from app.config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

EMBEDDING_DIM = 384
COLLECTIONS = [
    "conversation_embeddings",
    "workflow_embeddings",
    "knowledge_embeddings",
    "task_embeddings",
]

_client: AsyncQdrantClient | None = None


async def init_qdrant() -> None:
    global _client
    kwargs: dict = {"url": settings.QDRANT_URL}
    if settings.QDRANT_API_KEY:
        kwargs["api_key"] = settings.QDRANT_API_KEY

    _client = AsyncQdrantClient(**kwargs)

    # Ensure all required collections exist
    existing = {c.name for c in (await _client.get_collections()).collections}
    for name in COLLECTIONS:
        if name not in existing:
            await _client.create_collection(
                collection_name=name,
                vectors_config=VectorParams(size=EMBEDDING_DIM, distance=Distance.COSINE),
            )
            logger.info("qdrant_collection_created", collection=name)

    logger.info("qdrant_connected", collections=COLLECTIONS)


async def close_qdrant() -> None:
    global _client
    if _client:
        await _client.close()
    logger.info("qdrant_disconnected")


async def get_qdrant() -> AsyncQdrantClient:
    global _client
    if _client is None:
        await init_qdrant()
    assert _client is not None
    return _client


# Alias used by app.core.memory.episodic and tests
async def get_qdrant_client() -> AsyncQdrantClient:
    return await get_qdrant()
