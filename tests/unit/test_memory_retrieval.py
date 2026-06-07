"""Unit tests for cortexflow.memory.retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.memory.retrieval import (
    MemoryResult,
    MemoryRetrievalPipeline,
    RetrievalContext,
    _deduplicate,
)


# ---------------------------------------------------------------------------
# MemoryResult
# ---------------------------------------------------------------------------


def test_memory_result_defaults() -> None:
    r = MemoryResult(source="short_term", content="hello")
    assert r.score == 1.0
    assert r.metadata == {}


def test_memory_result_custom_score() -> None:
    r = MemoryResult(source="semantic", content={"text": "x"}, score=0.75)
    assert r.score == 0.75


# ---------------------------------------------------------------------------
# RetrievalContext
# ---------------------------------------------------------------------------


def test_retrieval_context_to_prompt_blocks() -> None:
    results = [
        MemoryResult(source="short_term", content="first", score=1.0),
        MemoryResult(source="semantic", content="second", score=0.8),
    ]
    ctx = RetrievalContext(results=results, token_estimate=10)
    blocks = ctx.to_prompt_blocks()
    assert len(blocks) == 2
    assert "[SHORT_TERM" in blocks[0]
    assert "first" in blocks[0]
    assert "[SEMANTIC" in blocks[1]


def test_retrieval_context_empty() -> None:
    ctx = RetrievalContext(results=[])
    assert ctx.to_prompt_blocks() == []
    assert ctx.token_estimate == 0


# ---------------------------------------------------------------------------
# _deduplicate
# ---------------------------------------------------------------------------


def test_deduplicate_removes_identical_content() -> None:
    results = [
        MemoryResult(source="short_term", content="same text", score=1.0),
        MemoryResult(source="semantic", content="same text", score=0.9),
        MemoryResult(source="long_term", content="same text", score=0.5),
    ]
    deduped = _deduplicate(results)
    assert len(deduped) == 1
    assert deduped[0].score == 1.0  # highest score wins


def test_deduplicate_keeps_distinct_content() -> None:
    results = [
        MemoryResult(source="short_term", content="alpha", score=1.0),
        MemoryResult(source="semantic", content="beta", score=0.9),
    ]
    deduped = _deduplicate(results)
    assert len(deduped) == 2


def test_deduplicate_empty_list() -> None:
    assert _deduplicate([]) == []


# ---------------------------------------------------------------------------
# MemoryRetrievalPipeline construction
# ---------------------------------------------------------------------------


def test_pipeline_default_construction() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="test-session")
    assert pipeline.session_id == "test-session"
    assert pipeline._redis_url == "redis://localhost:6379"
    assert pipeline._qdrant_url == "http://localhost:6333"


def test_pipeline_optional_session_id() -> None:
    pipeline = MemoryRetrievalPipeline()
    assert pipeline.session_id is None


# ---------------------------------------------------------------------------
# retrieve — tiers degrade gracefully when backends are unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_no_session_id_no_embedding_returns_empty() -> None:
    # With no session_id, short_term + long_term tiers are skipped.
    # With no embedding, semantic tier is also skipped.
    # Result must be an empty context, no error raised.
    pipeline = MemoryRetrievalPipeline()  # session_id=None

    ctx = await pipeline.retrieve("query")  # no embedding

    assert isinstance(ctx, RetrievalContext)
    assert ctx.results == []


@pytest.mark.asyncio
async def test_retrieve_top_k_capped() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s2")
    many = [MemoryResult(source="semantic", content=f"item-{i}", score=float(i) * 0.1) for i in range(20)]

    with (
        patch.object(pipeline, "_short_term", new=AsyncMock(return_value=[])),
        patch.object(pipeline, "_semantic", new=AsyncMock(return_value=many)),
        patch.object(pipeline, "_long_term", new=AsyncMock(return_value=[])),
    ):
        ctx = await pipeline.retrieve("query", embedding=[0.1] * 4, top_k=5)

    assert len(ctx.results) <= 5


@pytest.mark.asyncio
async def test_retrieve_score_ordered_descending() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s3")
    items = [
        MemoryResult(source="semantic", content="low", score=0.3),
        MemoryResult(source="semantic", content="high", score=0.9),
        MemoryResult(source="semantic", content="mid", score=0.6),
    ]

    with (
        patch.object(pipeline, "_short_term", new=AsyncMock(return_value=[])),
        patch.object(pipeline, "_semantic", new=AsyncMock(return_value=items)),
        patch.object(pipeline, "_long_term", new=AsyncMock(return_value=[])),
    ):
        ctx = await pipeline.retrieve("query", embedding=[0.1] * 4)

    scores = [r.score for r in ctx.results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_retrieve_deduplicates_cross_tier() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s4")
    duplicate = MemoryResult(source="short_term", content="dup text", score=1.0)
    also_dup = MemoryResult(source="semantic", content="dup text", score=0.7)

    with (
        patch.object(pipeline, "_short_term", new=AsyncMock(return_value=[duplicate])),
        patch.object(pipeline, "_semantic", new=AsyncMock(return_value=[also_dup])),
        patch.object(pipeline, "_long_term", new=AsyncMock(return_value=[])),
    ):
        ctx = await pipeline.retrieve("query", embedding=[0.1] * 4)

    contents = [r.content for r in ctx.results]
    assert contents.count("dup text") == 1


@pytest.mark.asyncio
async def test_retrieve_skips_disabled_tiers() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s5")
    st_mock = AsyncMock(return_value=[MemoryResult("short_term", "st", 1.0)])
    sem_mock = AsyncMock(return_value=[MemoryResult("semantic", "sem", 0.9)])
    lt_mock = AsyncMock(return_value=[MemoryResult("long_term", "lt", 0.5)])

    with (
        patch.object(pipeline, "_short_term", new=st_mock),
        patch.object(pipeline, "_semantic", new=sem_mock),
        patch.object(pipeline, "_long_term", new=lt_mock),
    ):
        ctx = await pipeline.retrieve(
            "query",
            embedding=[0.1] * 4,
            include_short_term=False,
            include_long_term=False,
        )

    st_mock.assert_not_called()
    lt_mock.assert_not_called()
    sem_mock.assert_called_once()
    assert len(ctx.results) == 1


# ---------------------------------------------------------------------------
# prune_low_importance — graceful degradation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_returns_dict_on_backend_failure() -> None:
    pipeline = MemoryRetrievalPipeline()

    # Both backends unavailable — should return zeros without raising
    result = await pipeline.prune_low_importance(importance_threshold=0.3)
    assert "pruned" in result
    assert "deduplicated" in result
    assert result["pruned"] == 0
    assert result["deduplicated"] == 0
