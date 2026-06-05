"""Unit tests for the memory subsystem.

All external I/O (Redis, Qdrant, Neo4j, SQLAlchemy) is mocked so tests
run fully offline without any infrastructure dependencies.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.core.memory.short_term import ShortTermMemory
from app.core.memory.long_term import LongTermMemory
from app.core.memory.episodic import EpisodicMemory
from app.core.memory.retrieval import MemoryRetrievalPipeline, MemoryResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_redis_mock(**overrides: object) -> AsyncMock:
    """Return a preconfigured Redis async mock."""
    mock = AsyncMock()
    mock.hset.return_value = 1
    mock.expire.return_value = True
    mock.hget.return_value = None
    mock.hgetall.return_value = {}
    mock.hdel.return_value = 1
    mock.delete.return_value = 1
    mock.rpush.return_value = 1
    mock.lrange.return_value = []
    mock.incrby.return_value = 5
    mock.get.return_value = None
    mock.ttl.return_value = 3500
    for attr, val in overrides.items():
        setattr(mock, attr, val)
    return mock


# ===========================================================================
# ShortTermMemory tests
# ===========================================================================

class TestShortTermMemory:
    """Tests for Redis-backed working memory."""

    @pytest.mark.asyncio
    async def test_set_stores_json_in_hash(self):
        redis = _make_redis_mock()
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            await stm.set("task", {"name": "research"})
        redis.hset.assert_called_once()
        _, args, kwargs = redis.hset.mock_calls[0]
        assert kwargs.get("key") == "task" or args[1] == "task"

    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self):
        redis = _make_redis_mock(hget=AsyncMock(return_value=None))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            result = await stm.get("missing_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_deserialises_json(self):
        payload = {"goal": "summarise document"}
        redis = _make_redis_mock(hget=AsyncMock(return_value=json.dumps(payload).encode()))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            result = await stm.get("goal")
        assert result == payload

    @pytest.mark.asyncio
    async def test_append_and_get_messages(self):
        msg = json.dumps({"role": "user", "content": "hello", "ts": "2024-01-01T00:00:00"}).encode()
        redis = _make_redis_mock(lrange=AsyncMock(return_value=[msg]))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            await stm.append_message("user", "hello")
            messages = await stm.get_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "user"
        assert messages[0]["content"] == "hello"

    @pytest.mark.asyncio
    async def test_increment_tokens_returns_new_total(self):
        redis = _make_redis_mock(incrby=AsyncMock(return_value=150))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            total = await stm.increment_tokens(50)
        assert total == 150

    @pytest.mark.asyncio
    async def test_get_token_count_returns_zero_when_missing(self):
        redis = _make_redis_mock(get=AsyncMock(return_value=None))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            count = await stm.get_token_count()
        assert count == 0

    @pytest.mark.asyncio
    async def test_ttl_remaining_delegates_to_redis(self):
        redis = _make_redis_mock(ttl=AsyncMock(return_value=1800))
        agent_id = uuid4()
        stm = ShortTermMemory(agent_id)
        with patch("app.core.memory.short_term.get_redis", new_callable=AsyncMock, return_value=redis):
            remaining = await stm.ttl_remaining()
        assert remaining == 1800


# ===========================================================================
# LongTermMemory tests
# ===========================================================================

class TestLongTermMemory:
    """Tests for PostgreSQL-backed persistent memory."""

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.add = MagicMock()
        session.flush = AsyncMock()
        return session

    @pytest.mark.asyncio
    async def test_store_adds_entry_to_session(self, mock_session):
        agent_id = uuid4()
        ltm = LongTermMemory(agent_id, mock_session)
        entry = await ltm.store({"text": "learned fact"}, memory_type="episodic")
        mock_session.add.assert_called_once()
        mock_session.flush.assert_called_once()
        assert entry.agent_id == agent_id
        assert entry.memory_type == "episodic"
        assert entry.content == {"text": "learned fact"}

    @pytest.mark.asyncio
    async def test_store_embedding_id_is_optional(self, mock_session):
        agent_id = uuid4()
        ltm = LongTermMemory(agent_id, mock_session)
        entry = await ltm.store({"text": "no embedding"})
        assert entry.embedding_id is None

    def test_importance_score_weighted_sum(self):
        score = LongTermMemory.importance_score(
            recency=1.0, access_count=50, relevance_score=0.8
        )
        # 0.4*1.0 + 0.3*0.5 + 0.3*0.8 = 0.4 + 0.15 + 0.24 = 0.79
        assert abs(score - 0.79) < 1e-9

    def test_importance_score_clamps_access_count(self):
        # access_count capped at 100 → normalised_access = 1.0
        score_capped = LongTermMemory.importance_score(
            recency=0.0, access_count=200, relevance_score=0.0
        )
        score_at_100 = LongTermMemory.importance_score(
            recency=0.0, access_count=100, relevance_score=0.0
        )
        assert abs(score_capped - score_at_100) < 1e-9

    def test_importance_score_all_zeros(self):
        score = LongTermMemory.importance_score(
            recency=0.0, access_count=0, relevance_score=0.0
        )
        assert score == 0.0

    def test_importance_score_all_max(self):
        score = LongTermMemory.importance_score(
            recency=1.0, access_count=100, relevance_score=1.0
        )
        assert abs(score - 1.0) < 1e-9


# ===========================================================================
# EpisodicMemory tests
# ===========================================================================

class TestEpisodicMemory:
    """Tests for Qdrant-backed semantic memory."""

    def _make_qdrant_mock(self) -> AsyncMock:
        mock = AsyncMock()
        mock.upsert.return_value = None
        mock.search.return_value = []
        mock.retrieve.return_value = []
        mock.delete.return_value = None
        return mock

    @pytest.mark.asyncio
    async def test_store_assigns_point_id(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            pid = await em.store(embedding=[0.1] * 384, payload={"text": "test"})
        assert isinstance(pid, str)
        assert len(pid) == 36  # UUID string length

    @pytest.mark.asyncio
    async def test_store_uses_provided_point_id(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        custom_id = "custom-point-id-001"
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            pid = await em.store(embedding=[0.1] * 384, payload={}, point_id=custom_id)
        assert pid == custom_id

    @pytest.mark.asyncio
    async def test_store_injects_agent_id_in_payload(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            await em.store(embedding=[0.0] * 384, payload={"foo": "bar"})
        call_args = client.upsert.call_args
        points = call_args.kwargs.get("points") or call_args.args[1]
        assert points[0].payload["agent_id"] == str(agent_id)

    @pytest.mark.asyncio
    async def test_search_returns_empty_on_no_hits(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            results = await em.search([0.0] * 384)
        assert results == []

    @pytest.mark.asyncio
    async def test_search_maps_hits_to_dicts(self):
        hit = MagicMock()
        hit.id = "abc-123"
        hit.score = 0.87
        hit.payload = {"text": "some memory"}
        client = self._make_qdrant_mock()
        client.search.return_value = [hit]
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            results = await em.search([0.0] * 384)
        assert len(results) == 1
        assert results[0]["score"] == 0.87
        assert results[0]["payload"] == {"text": "some memory"}

    @pytest.mark.asyncio
    async def test_store_batch_returns_correct_count(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        items = [([0.1] * 384, {"idx": i}) for i in range(5)]
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            ids = await em.store_batch(items)
        assert len(ids) == 5
        assert len(set(ids)) == 5  # all IDs are unique

    @pytest.mark.asyncio
    async def test_find_duplicates_delegates_to_search(self):
        client = self._make_qdrant_mock()
        agent_id = uuid4()
        em = EpisodicMemory(agent_id)
        with patch("app.core.memory.episodic.get_qdrant_client", new_callable=AsyncMock, return_value=client):
            dups = await em.find_duplicates([0.0] * 384, threshold=0.95)
        client.search.assert_called_once()
        assert isinstance(dups, list)


# ===========================================================================
# MemoryRetrievalPipeline tests
# ===========================================================================

class TestMemoryRetrievalPipeline:
    """Tests for the unified retrieval pipeline."""

    @pytest.mark.asyncio
    async def test_retrieve_returns_context_with_results(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {"goal": "write report"}
        stm_mock.get_messages.return_value = [{"role": "user", "content": "hi"}]

        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = [
            {"id": "p1", "score": 0.82, "payload": {"text": "related fact"}},
        ]

        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock

        ctx = await pipeline.retrieve("write a report", embedding=[0.0] * 384)
        assert ctx.token_estimate >= 0
        assert any(r.source == "short_term" for r in ctx.results)
        assert any(r.source == "episodic" for r in ctx.results)

    @pytest.mark.asyncio
    async def test_retrieve_skips_episodic_without_embedding(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []

        episodic_mock = AsyncMock()
        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock

        ctx = await pipeline.retrieve("query with no embedding", embedding=None)
        episodic_mock.search.assert_not_called()
        assert all(r.source != "episodic" for r in ctx.results)

    @pytest.mark.asyncio
    async def test_retrieve_deduplicates_identical_content(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []

        # Two Qdrant hits with identical payload
        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = [
            {"id": "p1", "score": 0.9, "payload": {"text": "same content"}},
            {"id": "p2", "score": 0.8, "payload": {"text": "same content"}},
        ]
        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock

        ctx = await pipeline.retrieve("q", embedding=[0.0] * 384)
        episodic_sources = [r for r in ctx.results if r.source == "episodic"]
        assert len(episodic_sources) == 1
        # Should keep the higher-scored one
        assert episodic_sources[0].score == 0.9

    @pytest.mark.asyncio
    async def test_retrieve_respects_top_k_cap(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {"k": "v"}
        stm_mock.get_messages.return_value = [{"role": "u", "content": "x"}]

        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = [
            {"id": f"p{i}", "score": 0.5 + i * 0.01, "payload": {"text": f"fact {i}"}}
            for i in range(20)
        ]
        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock

        ctx = await pipeline.retrieve("q", embedding=[0.0] * 384, top_k=5)
        assert len(ctx.results) <= 5

    def test_memory_result_to_prompt_blocks(self):
        results = [
            MemoryResult(source="short_term", content={"goal": "test"}, score=1.0),
            MemoryResult(source="episodic", content="some memory text", score=0.8),
        ]
        from app.core.memory.retrieval import RetrievalContext
        ctx = RetrievalContext(results=results, token_estimate=20)
        blocks = ctx.to_prompt_blocks()
        assert len(blocks) == 2
        assert "SHORT_TERM" in blocks[0]
        assert "EPISODIC" in blocks[1]

    @pytest.mark.asyncio
    async def test_store_episodic_skips_near_duplicate(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        episodic_mock = AsyncMock()
        # find_duplicates returns a hit — should skip storage
        episodic_mock.find_duplicates.return_value = [
            {"id": "existing", "score": 0.97, "payload": {}}
        ]
        pipeline._episodic = episodic_mock

        pid = await pipeline.store_episodic([0.0] * 384, {"text": "near dup"})
        assert pid is None
        episodic_mock.store.assert_not_called()

    @pytest.mark.asyncio
    async def test_retrieve_includes_graph_context(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []
        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = []
        
        graph_mock = AsyncMock()
        graph_mock.get_agent_tools.return_value = [{"name": "shell", "risk_level": "medium", "count": 5}]
        graph_mock.get_collaborating_agents.return_value = [{"id": str(uuid4()), "name": "assistant", "type": "subagent", "hops": 1}]

        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock
        pipeline._graph = graph_mock

        ctx = await pipeline.retrieve("query", embedding=[0.0] * 384, include_graph=True)
        graph_results = [r for r in ctx.results if r.source == "graph"]
        assert len(graph_results) == 2
        assert graph_results[0].metadata["namespace"] == "agent_tools"
        assert graph_results[1].metadata["namespace"] == "collaborating_agents"
        assert graph_mock.get_agent_tools.call_count == 1
        assert graph_mock.get_collaborating_agents.call_count == 1

    @pytest.mark.asyncio
    async def test_retrieve_includes_long_term_context(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []
        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = []
        graph_mock = AsyncMock()
        graph_mock.get_agent_tools.return_value = []
        graph_mock.get_collaborating_agents.return_value = []

        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock
        pipeline._graph = graph_mock

        db_mock = AsyncMock()
        mock_entry = MagicMock()
        mock_entry.id = uuid4()
        mock_entry.content = {"info": "persistent fact"}
        mock_entry.memory_type = "episodic"
        mock_entry.created_at = datetime.now(timezone.utc)

        ltm_instance = AsyncMock()
        ltm_instance.list.return_value = [mock_entry]

        with patch("app.core.memory.retrieval.LongTermMemory", return_value=ltm_instance):
            ctx = await pipeline.retrieve("query", embedding=[0.0] * 384, include_long_term=True, db=db_mock)
            
        ltm_results = [r for r in ctx.results if r.source == "long_term"]
        assert len(ltm_results) == 1
        assert ltm_results[0].content == {"info": "persistent fact"}
        assert ltm_results[0].metadata["memory_type"] == "episodic"

    @pytest.mark.asyncio
    async def test_retrieve_skips_long_term_when_db_is_none(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []
        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = []
        graph_mock = AsyncMock()
        graph_mock.get_agent_tools.return_value = []
        graph_mock.get_collaborating_agents.return_value = []

        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock
        pipeline._graph = graph_mock

        with patch("app.core.memory.retrieval.LongTermMemory") as mock_ltm_class:
            ctx = await pipeline.retrieve("query", embedding=[0.0] * 384, include_long_term=True, db=None)
            mock_ltm_class.assert_not_called()

        ltm_results = [r for r in ctx.results if r.source == "long_term"]
        assert len(ltm_results) == 0

    @pytest.mark.asyncio
    async def test_retrieve_skips_graph_and_long_term_when_disabled(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        stm_mock = AsyncMock()
        stm_mock.get_all.return_value = {}
        stm_mock.get_messages.return_value = []
        episodic_mock = AsyncMock()
        episodic_mock.search.return_value = []
        graph_mock = AsyncMock()
        graph_mock.get_agent_tools.return_value = []
        graph_mock.get_collaborating_agents.return_value = []

        pipeline._stm = stm_mock
        pipeline._episodic = episodic_mock
        pipeline._graph = graph_mock

        db_mock = AsyncMock()
        with patch("app.core.memory.retrieval.LongTermMemory") as mock_ltm_class:
            ctx = await pipeline.retrieve("query", embedding=[0.0] * 384, include_graph=False, include_long_term=False, db=db_mock)
            mock_ltm_class.assert_not_called()
            graph_mock.get_agent_tools.assert_not_called()

        assert not any(r.source in ("graph", "long_term") for r in ctx.results)

    @pytest.mark.asyncio
    async def test_store_episodic_stores_when_no_duplicate(self):
        agent_id = uuid4()
        pipeline = MemoryRetrievalPipeline(agent_id)

        episodic_mock = AsyncMock()
        episodic_mock.find_duplicates.return_value = []
        episodic_mock.store.return_value = "new-point-id"
        pipeline._episodic = episodic_mock

        pid = await pipeline.store_episodic([0.0] * 384, {"text": "unique content"})
        assert pid == "new-point-id"
        episodic_mock.store.assert_called_once()


