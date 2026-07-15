"""Per-node memory namespace isolation for AgentOrchestrator.

Each orchestrator node is assigned an effective_memory_namespace (defaults to
its own name).  This module provides a lightweight, in-process key-value store
that is keyed by namespace, letting multiple nodes share the same
MemoryNamespaceManager instance while keeping their memories completely
separated.

In production the gateway wires a single MemoryNamespaceManager into the
orchestrator so that routed tasks can read and write memory entries without
crossing node boundaries.  The manager is deliberately simple — it is not a
replacement for the full 3-tier memory stack (Redis + Qdrant + SQLite) but a
namespace-routing shim that prefixes all downstream memory operations.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)

# Maximum entries stored per namespace before the oldest entry is evicted.
_DEFAULT_MAX_ENTRIES = 1000


@dataclass
class MemoryEntry:
    """A single memory record stored within a namespace."""

    key: str
    value: Any
    namespace: str
    created_at: float = field(default_factory=time.monotonic)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "value": self.value,
            "namespace": self.namespace,
            "created_at": self.created_at,
            "tags": self.tags,
        }


class MemoryNamespaceStore:
    """Ordered key-value store for a single namespace.

    Args:
        namespace:   Identifier for this store (e.g. the node name).
        max_entries: LRU-style cap; oldest entry evicted when exceeded.
    """

    def __init__(self, namespace: str, max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        if not namespace:
            raise ValueError("MemoryNamespaceStore: namespace must not be empty")
        self.namespace = namespace
        self.max_entries = max_entries
        self._store: dict[str, MemoryEntry] = {}

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def put(self, key: str, value: Any, tags: list[str] | None = None) -> MemoryEntry:
        """Insert or replace an entry.  Evicts the oldest entry when full."""
        if not key:
            raise ValueError("MemoryNamespaceStore.put: key must not be empty")
        entry = MemoryEntry(
            key=key,
            value=value,
            namespace=self.namespace,
            tags=tags or [],
        )
        if key in self._store:
            del self._store[key]
        elif len(self._store) >= self.max_entries:
            oldest_key = next(iter(self._store))
            del self._store[oldest_key]
            log.debug("namespace=%s evicted key=%s (max_entries=%d)", self.namespace, oldest_key, self.max_entries)
        self._store[key] = entry
        return entry

    def get(self, key: str) -> MemoryEntry | None:
        """Return the entry for *key*, or ``None`` if not found."""
        return self._store.get(key)

    def delete(self, key: str) -> bool:
        """Delete an entry by key.  Returns ``True`` if it existed."""
        if key in self._store:
            del self._store[key]
            return True
        return False

    def search(self, query: str, *, tag: str | None = None) -> list[MemoryEntry]:
        """Return entries whose key or string value contains *query*.

        Optionally filter to entries that carry *tag*.
        """
        q = query.lower()
        results = []
        for entry in self._store.values():
            if tag and tag not in entry.tags:
                continue
            if q in entry.key.lower() or q in str(entry.value).lower():
                results.append(entry)
        return results

    def list_by_tag(self, tag: str) -> list[MemoryEntry]:
        """Return all entries carrying *tag*."""
        return [e for e in self._store.values() if tag in e.tags]

    def clear(self) -> int:
        """Remove all entries.  Returns the number of entries removed."""
        count = len(self._store)
        self._store.clear()
        return count

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def count(self) -> int:
        """Number of entries currently stored."""
        return len(self._store)

    def all_entries(self) -> list[MemoryEntry]:
        """Return all entries in insertion order."""
        return list(self._store.values())

    def all_keys(self) -> list[str]:
        """Return all keys in insertion order."""
        return list(self._store.keys())

    def stats(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "count": self.count(),
            "max_entries": self.max_entries,
            "utilization": round(self.count() / self.max_entries, 4) if self.max_entries else 0,
        }


class MemoryNamespaceManager:
    """Registry of per-namespace :class:`MemoryNamespaceStore` instances.

    Each orchestrator node that calls :meth:`namespace` gets a dedicated store.
    Nodes that share the same ``effective_memory_namespace`` (e.g. two nodes
    explicitly set to the same namespace) share one store.

    Args:
        default_max_entries: Per-store entry cap applied to newly created stores.
    """

    def __init__(self, default_max_entries: int = _DEFAULT_MAX_ENTRIES) -> None:
        self.default_max_entries = default_max_entries
        self._stores: dict[str, MemoryNamespaceStore] = {}

    # ------------------------------------------------------------------
    # Namespace access
    # ------------------------------------------------------------------

    def namespace(self, ns: str) -> MemoryNamespaceStore:
        """Return the store for *ns*, creating it on first access."""
        if not ns:
            raise ValueError("MemoryNamespaceManager.namespace: ns must not be empty")
        if ns not in self._stores:
            self._stores[ns] = MemoryNamespaceStore(ns, self.default_max_entries)
            log.debug("memory_namespace_manager created namespace=%s", ns)
        return self._stores[ns]

    # ------------------------------------------------------------------
    # Convenience pass-throughs (operate on a named namespace)
    # ------------------------------------------------------------------

    def put(self, ns: str, key: str, value: Any, tags: list[str] | None = None) -> MemoryEntry:
        return self.namespace(ns).put(key, value, tags)

    def get(self, ns: str, key: str) -> MemoryEntry | None:
        return self.namespace(ns).get(key)

    def delete(self, ns: str, key: str) -> bool:
        return self.namespace(ns).delete(key)

    def search(self, ns: str, query: str, *, tag: str | None = None) -> list[MemoryEntry]:
        return self.namespace(ns).search(query, tag=tag)

    def clear_namespace(self, ns: str) -> int:
        """Clear all entries in *ns*.  Returns the count removed."""
        if ns not in self._stores:
            return 0
        return self._stores[ns].clear()

    def drop_namespace(self, ns: str) -> bool:
        """Remove the store for *ns* entirely.  Returns True if it existed."""
        if ns in self._stores:
            del self._stores[ns]
            return True
        return False

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def list_namespaces(self) -> list[str]:
        """Return all known namespace names."""
        return list(self._stores.keys())

    def namespace_count(self) -> int:
        """Number of distinct namespaces currently managed."""
        return len(self._stores)

    def global_stats(self) -> dict[str, Any]:
        """Return aggregated stats across all namespaces."""
        stores = list(self._stores.values())
        total = sum(s.count() for s in stores)
        return {
            "namespace_count": len(stores),
            "total_entries": total,
            "namespaces": [s.stats() for s in stores],
        }

    def namespace_stats(self, ns: str) -> dict[str, Any] | None:
        """Return stats for *ns*, or ``None`` if it does not exist."""
        store = self._stores.get(ns)
        return store.stats() if store else None
