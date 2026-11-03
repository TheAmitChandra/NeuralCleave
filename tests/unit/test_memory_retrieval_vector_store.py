"""In-memory vector store: dimension-mismatch handling."""

from __future__ import annotations

from neuralcleave.memory.retrieval import _InMemoryVectorStore


def test_search_skips_vectors_with_different_dimension() -> None:
    store = _InMemoryVectorStore()
    store.upsert("short", [1.0, 0.0], {"t": "short"})
    store.upsert("match", [1.0, 0.0, 0.0], {"t": "match"})
    results = store.search([1.0, 0.0, 0.0], top_k=5, threshold=0.0)
    assert [r[0] for r in results] == ["match"]


def test_search_scores_matching_dimension_normally() -> None:
    store = _InMemoryVectorStore()
    store.upsert("a", [1.0, 0.0], {})
    (pid, _payload, score), = store.search([1.0, 0.0], top_k=1, threshold=0.5)
    assert pid == "a"
    assert abs(score - 1.0) < 1e-9
