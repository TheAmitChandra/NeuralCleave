"""Unit tests for cortexflow.memory.retrieval."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.memory.retrieval import (
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
    # With no session_id, short_term is skipped (it's keyed by session).
    # With no embedding, semantic tier is also skipped. Long-term is
    # patched here to isolate from real disk state; its cross-session
    # behavior is covered separately above.
    pipeline = MemoryRetrievalPipeline()  # session_id=None

    with patch.object(pipeline, "_long_term", new=AsyncMock(return_value=[])):
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
# Cross-session memory sharing — long-term tier ignores session_id=None
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_long_term_tier_attempted_even_without_session_id() -> None:
    pipeline = MemoryRetrievalPipeline()  # session_id=None
    lt_mock = AsyncMock(return_value=[MemoryResult("long_term", "shared memory", 0.8)])

    with patch.object(pipeline, "_long_term", new=lt_mock):
        ctx = await pipeline.retrieve("query")

    lt_mock.assert_called_once()
    assert len(ctx.results) == 1
    assert ctx.results[0].content == "shared memory"


@pytest.mark.asyncio
async def test_long_term_cross_session_query_returns_all_sessions(tmp_path) -> None:
    from cortexflow_ai.memory.long_term import LongTermMemory

    db_path = tmp_path / "shared.db"
    lt = LongTermMemory(db_path=str(db_path))
    await lt.init_schema()
    await lt.store("telegram-session", "learned via telegram", importance=0.7)
    await lt.store("discord-session", "learned via discord", importance=0.6)

    pipeline = MemoryRetrievalPipeline(sqlite_path=str(db_path))  # session_id=None

    results = await pipeline._long_term(limit=10)

    contents = {r.content for r in results}
    assert contents == {"learned via telegram", "learned via discord"}


@pytest.mark.asyncio
async def test_long_term_failure_returns_empty_list() -> None:
    pipeline = MemoryRetrievalPipeline(sqlite_path="~/.cortexflow/memory.db")

    with patch("aiosqlite.connect", side_effect=Exception("disk error")):
        results = await pipeline._long_term(limit=10)

    assert results == []


@pytest.mark.asyncio
async def test_long_term_with_session_id_stays_scoped(tmp_path) -> None:
    from cortexflow_ai.memory.long_term import LongTermMemory

    db_path = tmp_path / "scoped.db"
    lt = LongTermMemory(db_path=str(db_path))
    await lt.init_schema()
    await lt.store("session-a", "a's memory", importance=0.7)
    await lt.store("session-b", "b's memory", importance=0.6)

    pipeline = MemoryRetrievalPipeline(session_id="session-a", sqlite_path=str(db_path))

    results = await pipeline._long_term(limit=10)

    assert len(results) == 1
    assert results[0].content == "a's memory"


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


# ---------------------------------------------------------------------------
# store_short_term — Redis (mocked, package not installed)
# ---------------------------------------------------------------------------


def _mock_redis_module(client: MagicMock) -> dict:
    # `import redis.asyncio as aioredis` resolves via getattr(redis, "asyncio"),
    # not sys.modules["redis.asyncio"] directly — the parent mock needs the
    # submodule wired on as a real attribute, not an auto-generated one.
    mock_aioredis = MagicMock()
    mock_aioredis.from_url = AsyncMock(return_value=client)
    mock_redis_parent = MagicMock()
    mock_redis_parent.asyncio = mock_aioredis
    return {"redis": mock_redis_parent, "redis.asyncio": mock_aioredis}


@pytest.mark.asyncio
async def test_store_short_term_success() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s1")
    mock_client = MagicMock()
    mock_client.set = AsyncMock()
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        await pipeline.store_short_term("last_topic", {"value": "python"})

    mock_client.set.assert_called_once()
    call_args = mock_client.set.call_args
    assert call_args[0][0] == "cf:stm:s1:last_topic"
    mock_client.aclose.assert_called_once()


@pytest.mark.asyncio
async def test_store_short_term_failure_does_not_raise() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s1")
    await pipeline.store_short_term("key", "value")  # redis not installed -> swallowed


# ---------------------------------------------------------------------------
# store_semantic — Qdrant (mocked, package not installed)
# ---------------------------------------------------------------------------


def _mock_qdrant_module(client: MagicMock) -> dict:
    mock_qdrant_client = MagicMock()
    mock_qdrant_client.QdrantClient = MagicMock(return_value=client)
    mock_models = MagicMock()
    mock_models.PointStruct = MagicMock(side_effect=lambda **kw: kw)
    return {"qdrant_client": mock_qdrant_client, "qdrant_client.models": mock_models}


@pytest.mark.asyncio
async def test_store_semantic_returns_point_id() -> None:
    pipeline = MemoryRetrievalPipeline()
    mock_client = MagicMock()
    mock_client.upsert = MagicMock()

    with patch.dict("sys.modules", _mock_qdrant_module(mock_client)):
        point_id = await pipeline.store_semantic([0.1, 0.2], {"text": "hello"})

    assert point_id is not None
    mock_client.upsert.assert_called_once()


@pytest.mark.asyncio
async def test_store_semantic_failure_returns_none() -> None:
    pipeline = MemoryRetrievalPipeline()
    point_id = await pipeline.store_semantic([0.1], {})  # qdrant not installed
    assert point_id is None


# ---------------------------------------------------------------------------
# _short_term — real implementation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_term_returns_matching_keys() -> None:
    import json

    pipeline = MemoryRetrievalPipeline(session_id="s1")
    mock_client = MagicMock()
    mock_client.keys = AsyncMock(return_value=["cf:stm:s1:topic"])
    mock_client.get = AsyncMock(return_value=json.dumps({"value": "x"}))
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        results = await pipeline._short_term("query")

    assert len(results) == 1
    assert results[0].source == "short_term"
    assert results[0].content == {"value": "x"}


@pytest.mark.asyncio
async def test_short_term_no_keys_returns_empty() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s1")
    mock_client = MagicMock()
    mock_client.keys = AsyncMock(return_value=[])
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        results = await pipeline._short_term("query")

    assert results == []


@pytest.mark.asyncio
async def test_short_term_failure_returns_empty() -> None:
    pipeline = MemoryRetrievalPipeline(session_id="s1")
    results = await pipeline._short_term("query")  # redis not installed
    assert results == []


# ---------------------------------------------------------------------------
# _semantic — real implementation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_semantic_returns_hits() -> None:
    pipeline = MemoryRetrievalPipeline()
    hit = MagicMock()
    hit.payload = {"text": "semantic match"}
    hit.score = 0.85
    hit.id = "point-1"

    mock_client = MagicMock()
    mock_client.search = MagicMock(return_value=[hit])

    with patch.dict("sys.modules", _mock_qdrant_module(mock_client)):
        results = await pipeline._semantic([0.1, 0.2], top_k=5, threshold=0.5)

    assert len(results) == 1
    assert results[0].source == "semantic"
    assert results[0].score == 0.85


@pytest.mark.asyncio
async def test_semantic_failure_returns_empty() -> None:
    pipeline = MemoryRetrievalPipeline()
    results = await pipeline._semantic([0.1], top_k=5, threshold=0.5)  # qdrant not installed
    assert results == []


# ---------------------------------------------------------------------------
# prune_low_importance — sqlite success + Qdrant dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_low_importance_sqlite_removes_rows(tmp_path) -> None:
    from cortexflow_ai.memory.long_term import LongTermMemory

    db_path = tmp_path / "prune.db"
    lt = LongTermMemory(db_path=str(db_path))
    await lt.init_schema()
    await lt.store("s1", "keep", importance=0.9)
    await lt.store("s1", "drop", importance=0.1)

    pipeline = MemoryRetrievalPipeline(sqlite_path=str(db_path))
    result = await pipeline.prune_low_importance(importance_threshold=0.3)

    assert result["pruned"] == 1


@pytest.mark.asyncio
async def test_prune_low_importance_qdrant_deduplicates() -> None:
    pipeline = MemoryRetrievalPipeline()

    dup_point = MagicMock()
    dup_point.id = "point-1"
    dup_point2 = MagicMock()
    dup_point2.id = "point-1"  # duplicate ID
    unique_point = MagicMock()
    unique_point.id = "point-2"

    mock_client = MagicMock()
    mock_client.scroll = MagicMock(return_value=([dup_point, dup_point2, unique_point], None))
    mock_client.delete = MagicMock()

    with patch.dict("sys.modules", _mock_qdrant_module(mock_client)):
        result = await pipeline.prune_low_importance(importance_threshold=0.3)

    assert result["deduplicated"] == 1
    mock_client.delete.assert_called_once()


@pytest.mark.asyncio
async def test_prune_low_importance_qdrant_no_duplicates_skips_delete() -> None:
    pipeline = MemoryRetrievalPipeline()

    point1 = MagicMock()
    point1.id = "point-1"
    point2 = MagicMock()
    point2.id = "point-2"

    mock_client = MagicMock()
    mock_client.scroll = MagicMock(return_value=([point1, point2], None))
    mock_client.delete = MagicMock()

    with patch.dict("sys.modules", _mock_qdrant_module(mock_client)):
        result = await pipeline.prune_low_importance(importance_threshold=0.3)

    assert result["deduplicated"] == 0
    mock_client.delete.assert_not_called()


# ---------------------------------------------------------------------------
# _long_term — query forwarding
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_long_term_filters_by_query_returns_matching_rows(tmp_path) -> None:
    """_long_term(query=...) must apply a LIKE filter, not return every row."""
    from cortexflow_ai.memory.long_term import LongTermMemory

    db_path = tmp_path / "filter.db"
    lt = LongTermMemory(db_path=str(db_path))
    await lt.init_schema()
    await lt.store("s1", "Python asyncio tutorial", importance=0.7)
    await lt.store("s1", "JavaScript promises guide", importance=0.8)

    pipeline = MemoryRetrievalPipeline(sqlite_path=str(db_path))

    results = await pipeline._long_term(limit=10, query="asyncio")

    assert len(results) == 1
    assert "asyncio" in results[0].content


@pytest.mark.asyncio
async def test_long_term_empty_query_returns_all_rows(tmp_path) -> None:
    """_long_term(query='') must not apply a LIKE filter — return all rows."""
    from cortexflow_ai.memory.long_term import LongTermMemory

    db_path = tmp_path / "all.db"
    lt = LongTermMemory(db_path=str(db_path))
    await lt.init_schema()
    await lt.store("s1", "entry one", importance=0.5)
    await lt.store("s1", "entry two", importance=0.6)

    pipeline = MemoryRetrievalPipeline(sqlite_path=str(db_path))

    results = await pipeline._long_term(limit=10, query="")

    assert len(results) == 2


@pytest.mark.asyncio
async def test_retrieve_forwards_query_to_long_term_tier() -> None:
    """retrieve() must forward the query string to _long_term(), not drop it."""
    pipeline = MemoryRetrievalPipeline()
    lt_mock = AsyncMock(return_value=[])

    with (
        patch.object(pipeline, "_short_term", new=AsyncMock(return_value=[])),
        patch.object(pipeline, "_long_term", new=lt_mock),
    ):
        await pipeline.retrieve("specific query text", top_k=5)

    lt_mock.assert_called_once_with(limit=5, query="specific query text", session_id=None)


# ---------------------------------------------------------------------------
# session_id override in retrieve() / store_short_term() / _short_term()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_retrieve_session_id_override_takes_precedence_over_self() -> None:
    """Per-call session_id overrides the pipeline's self.session_id."""
    pipeline = MemoryRetrievalPipeline(session_id="default-sid")
    st_mock = AsyncMock(return_value=[])
    lt_mock = AsyncMock(return_value=[])

    with (
        patch.object(pipeline, "_short_term", new=st_mock),
        patch.object(pipeline, "_long_term", new=lt_mock),
    ):
        await pipeline.retrieve("q", session_id="override-sid")

    st_mock.assert_called_once_with("q", session_id="override-sid")
    lt_mock.assert_called_once_with(limit=10, query="q", session_id="override-sid")


@pytest.mark.asyncio
async def test_retrieve_uses_self_session_id_when_override_is_none() -> None:
    """When override is None, self.session_id is used."""
    pipeline = MemoryRetrievalPipeline(session_id="self-sid")
    st_mock = AsyncMock(return_value=[])
    lt_mock = AsyncMock(return_value=[])

    with (
        patch.object(pipeline, "_short_term", new=st_mock),
        patch.object(pipeline, "_long_term", new=lt_mock),
    ):
        await pipeline.retrieve("q")  # no override

    st_mock.assert_called_once_with("q", session_id="self-sid")
    lt_mock.assert_called_once_with(limit=10, query="q", session_id="self-sid")


@pytest.mark.asyncio
async def test_store_short_term_session_id_override() -> None:
    """store_short_term(session_id=...) overrides self.session_id in the Redis key."""
    pipeline = MemoryRetrievalPipeline(session_id="default-sid")
    mock_client = MagicMock()
    mock_client.set = AsyncMock()
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        await pipeline.store_short_term("k", "v", session_id="override-sid")

    call_key = mock_client.set.call_args[0][0]
    assert "override-sid" in call_key
    assert "default-sid" not in call_key


@pytest.mark.asyncio
async def test_store_short_term_skips_when_no_session_id_resolvable() -> None:
    """store_short_term skips (no error) when both self.session_id and override are None."""
    pipeline = MemoryRetrievalPipeline()  # session_id=None
    mock_client = MagicMock()
    mock_client.set = AsyncMock()
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        await pipeline.store_short_term("k", "v")  # no override, no self.session_id

    mock_client.set.assert_not_called()


@pytest.mark.asyncio
async def test_short_term_override_uses_correct_pattern() -> None:
    """_short_term(session_id=...) scans the override session's Redis keys."""
    import json

    pipeline = MemoryRetrievalPipeline(session_id="default-sid")
    mock_client = MagicMock()
    mock_client.keys = AsyncMock(return_value=["cf:stm:override-sid:t1"])
    mock_client.get = AsyncMock(return_value=json.dumps({"v": 1}))
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        results = await pipeline._short_term("q", session_id="override-sid")

    pattern_used = mock_client.keys.call_args[0][0]
    assert "override-sid" in pattern_used
    assert "default-sid" not in pattern_used
    assert len(results) == 1


@pytest.mark.asyncio
async def test_short_term_returns_empty_when_no_session_id() -> None:
    """_short_term returns [] immediately if neither override nor self.session_id is set."""
    pipeline = MemoryRetrievalPipeline()  # session_id=None
    mock_client = MagicMock()
    mock_client.keys = AsyncMock(return_value=[])
    mock_client.aclose = AsyncMock()

    with patch.dict("sys.modules", _mock_redis_module(mock_client)):
        results = await pipeline._short_term("q")  # no override

    mock_client.keys.assert_not_called()
    assert results == []
