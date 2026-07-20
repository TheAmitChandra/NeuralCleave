"""NeuralCleave Memory SDK — abstract interface for custom memory backends.

Plugin authors can implement a custom memory backend by subclassing
:class:`MemoryBackendSDK` and registering it with :class:`MemoryRegistry`.
The backend is then available to the retrieval pipeline as an extra memory tier.

Architecture
────────────
                  ┌───────────────────────────┐
    Plugin file   │  class MyMemoryBackend     │
                  │    (MemoryBackendSDK):     │
                  │    async store(...)  → None│
                  │    async retrieve(.)→ list │
                  │    async delete(...)→ None │
                  └────────────┬──────────────┘
                               │ MemoryRegistry.register(MyMemoryBackend)
                  ┌────────────▼──────────────┐
                  │     MemoryRegistry        │  ← SDK singleton catalogue
                  └──────────────────────────-┘
                               │  used by RetrievalPipeline (existing module)
                               ▼

Usage — class-based backend::

    from app.sdk import MemoryBackendSDK, MemoryRegistry, MemoryRecord

    class MyVectorBackend(MemoryBackendSDK):
        tier = "my_vector_store"

        async def store(self, record: MemoryRecord) -> None:
            await my_vector_db.insert(record.content, record.metadata)

        async def retrieve(
            self, query: str, *, agent_id: str, top_k: int = 5
        ) -> list[MemoryRecord]:
            results = await my_vector_db.search(query, top_k=top_k)
            return [MemoryRecord(content=r["text"], score=r["score"]) for r in results]

        async def delete(self, memory_id: str) -> None:
            await my_vector_db.delete(memory_id)

    MemoryRegistry.register(MyVectorBackend())
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.observability.logs import get_logger

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class MemoryRecord:
    """A single memory item returned from or stored to a backend.

    Attributes
    ----------
    content:     The stored text, dict, or blob.
    memory_id:   Optional stable identifier (UUID string preferred).
    score:       Relevance score in [0, 1]. Higher = more relevant.
    metadata:    Arbitrary key-value metadata (agent_id, timestamp, tags, …).
    """

    content: Any
    memory_id: str = ""
    score: float = 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def source(self) -> str:
        """Convenience: read the source tier from metadata."""
        return self.metadata.get("source", "unknown")


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class MemoryBackendSDK(ABC):
    """Abstract base class for a NeuralCleave memory backend plugin.

    Subclass this, set :attr:`tier` to a unique name, implement the three
    abstract coroutines, then register with :class:`MemoryRegistry`.

    Class attributes
    ────────────────
    tier          Unique string identifier for this memory tier.
                  Used as the ``source`` label in :class:`MemoryRecord`.
    priority      Used by the retrieval pipeline for result ranking.
                  Lower = checked earlier / considered more authoritative.
    """

    tier: str = ""
    priority: int = 100

    @abstractmethod
    async def store(self, record: MemoryRecord) -> None:
        """Persist *record* in this backend.

        Parameters
        ----------
        record:
            The memory item to store. ``memory_id`` may be empty —
            generate one if required by the backend.
        """

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        agent_id: str,
        top_k: int = 5,
    ) -> list[MemoryRecord]:
        """Return up to *top_k* records relevant to *query* for *agent_id*.

        Parameters
        ----------
        query:
            Free-text search query.
        agent_id:
            Scope retrieval to this agent's memory space.
        top_k:
            Maximum number of records to return.

        Returns
        -------
        list[MemoryRecord]
            Ordered by relevance (highest score first).
        """

    @abstractmethod
    async def delete(self, memory_id: str) -> None:
        """Permanently remove the memory item identified by *memory_id*.

        Parameters
        ----------
        memory_id:
            The same identifier that was set (or generated) during
            :meth:`store`.  Silently ignore if not found.
        """

    async def health_check(self) -> bool:
        """Return True if this backend is reachable and healthy.

        Override to add real connectivity checks (ping, SELECT 1, etc.).
        Defaults to True (assume healthy) for convenience.
        """
        return True


# ---------------------------------------------------------------------------
# MemoryRegistry
# ---------------------------------------------------------------------------


class MemoryRegistry:
    """Catalogue of registered custom memory backends.

    All registered backends are available to the NeuralCleave retrieval
    pipeline as extra memory tiers alongside the built-in Redis / PostgreSQL /
    Qdrant / Neo4j tiers.

    Usage::

        MemoryRegistry.register(MyVectorBackend())
        backends = MemoryRegistry.list_backends()
        backend  = MemoryRegistry.get("my_vector_store")
    """

    _registry: dict[str, MemoryBackendSDK] = {}

    @classmethod
    def register(cls, backend: MemoryBackendSDK) -> None:
        """Register *backend* in the catalogue.

        Raises
        ------
        ValueError
            If ``backend.tier`` is empty or already registered.
        """
        if not backend.tier:
            raise ValueError(
                f"{backend.__class__.__name__} must set tier attribute before registering"
            )
        if backend.tier in cls._registry:
            raise ValueError(
                f"Memory backend '{backend.tier}' is already registered. "
                "Unregister first or choose a different tier name."
            )
        cls._registry[backend.tier] = backend
        logger.info("sdk.memory_backend_registered", tier=backend.tier, priority=backend.priority)

    @classmethod
    def unregister(cls, tier: str) -> None:
        """Remove the backend registered under *tier*. Silent if not found."""
        cls._registry.pop(tier, None)

    @classmethod
    def get(cls, tier: str) -> MemoryBackendSDK | None:
        """Return the backend registered under *tier*, or ``None``."""
        return cls._registry.get(tier)

    @classmethod
    def list_backends(cls) -> list[MemoryBackendSDK]:
        """Return all registered backends sorted by priority (lowest first)."""
        return sorted(cls._registry.values(), key=lambda b: b.priority)

    @classmethod
    def list_tiers(cls) -> list[str]:
        """Return all registered tier names."""
        return list(cls._registry.keys())
