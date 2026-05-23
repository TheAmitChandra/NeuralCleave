"""Benchmarks for the memory system hot paths.

Covers:
  - ShortTermMemory key construction (_key helper)
  - RetrievalContext.to_prompt_blocks serialisation
  - MemoryResult instantiation
  - MemoryRetrievalPipeline deduplication
  - Retrieval pipeline (short-term-only, no I/O)
  - Message history JSON encoding/decoding
"""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest

from tests.benchmarks.conftest import run_async
from app.core.memory.short_term import ShortTermMemory, _key
from app.core.memory.retrieval import MemoryResult, MemoryRetrievalPipeline, RetrievalContext


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def agent_id() -> UUID:
    return uuid.UUID("12345678-1234-5678-1234-567812345678")


@pytest.fixture
def stm(agent_id) -> ShortTermMemory:
    return ShortTermMemory(agent_id)


@pytest.fixture
def results_10() -> list[MemoryResult]:
    return [
        MemoryResult(source="short_term", content=f"context item {i}", score=1.0 - i * 0.05)
        for i in range(10)
    ]


@pytest.fixture
def results_100() -> list[MemoryResult]:
    return [
        MemoryResult(source="episodic", content=f"memory chunk {i}", score=round(1.0 - i * 0.009, 3))
        for i in range(100)
    ]


# ---------------------------------------------------------------------------
# BenchKeyConstruction — pure Python, no I/O
# ---------------------------------------------------------------------------

class BenchKeyConstruction:
    def bench_key_default_namespace(self, benchmark, agent_id):
        benchmark(_key, agent_id)

    def bench_key_custom_namespace(self, benchmark, agent_id):
        benchmark(_key, agent_id, "messages")

    def bench_stm_init(self, benchmark, agent_id):
        benchmark(ShortTermMemory, agent_id)

    def bench_stm_init_custom_ttl(self, benchmark, agent_id):
        benchmark(ShortTermMemory, agent_id, 7200)


# ---------------------------------------------------------------------------
# BenchMemoryResult — dataclass operations
# ---------------------------------------------------------------------------

class BenchMemoryResult:
    def bench_result_creation_minimal(self, benchmark):
        benchmark(MemoryResult, source="short_term", content="hello world")

    def bench_result_creation_full(self, benchmark):
        benchmark(
            MemoryResult,
            source="episodic",
            content={"role": "assistant", "text": "Here is the answer."},
            score=0.87,
            metadata={"ts": "2025-01-01T00:00:00", "agent": "planner"},
        )

    def bench_result_creation_batch_10(self, benchmark):
        def _make_batch():
            return [
                MemoryResult(source="long_term", content=f"item {i}", score=0.9 - i * 0.01)
                for i in range(10)
            ]
        benchmark(_make_batch)


# ---------------------------------------------------------------------------
# BenchRetrievalContext — serialisation hot paths
# ---------------------------------------------------------------------------

class BenchRetrievalContext:
    def bench_to_prompt_blocks_10(self, benchmark, results_10):
        ctx = RetrievalContext(results=results_10, token_estimate=200)
        benchmark(ctx.to_prompt_blocks)

    def bench_to_prompt_blocks_100(self, benchmark, results_100):
        ctx = RetrievalContext(results=results_100, token_estimate=2000)
        benchmark(ctx.to_prompt_blocks)

    def bench_context_creation(self, benchmark, results_10):
        benchmark(RetrievalContext, results=results_10, token_estimate=200)

    def bench_token_estimation(self, benchmark, results_100):
        def _estimate(results):
            return sum(len(str(r.content)) // 4 for r in results)
        benchmark(_estimate, results_100)


# ---------------------------------------------------------------------------
# BenchDeduplication — pipeline internal logic (no I/O)
# ---------------------------------------------------------------------------

class BenchDeduplication:
    def bench_deduplicate_no_dupes_10(self, benchmark, agent_id, results_10):
        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        benchmark(pipeline._deduplicate, results_10)

    def bench_deduplicate_50pct_dupes(self, benchmark, agent_id):
        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        base = [MemoryResult(source="episodic", content=f"item {i}", score=0.9) for i in range(10)]
        with_dupes = base + base  # 50% duplicates
        benchmark(pipeline._deduplicate, with_dupes)

    def bench_deduplicate_all_dupes(self, benchmark, agent_id):
        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        same = [MemoryResult(source="episodic", content="identical content", score=0.9)] * 20
        benchmark(pipeline._deduplicate, same)

    def bench_sort_and_cap(self, benchmark, results_100):
        def _sort_cap(results):
            results.sort(key=lambda r: r.score, reverse=True)
            return results[:10]
        benchmark(_sort_cap, list(results_100))


# ---------------------------------------------------------------------------
# BenchMessageEncoding — JSON hot path for message history
# ---------------------------------------------------------------------------

class BenchMessageEncoding:
    def bench_encode_single_message(self, benchmark):
        entry = {"role": "user", "content": "What is the status of the deployment?", "ts": "2025-01-01T10:00:00"}
        benchmark(json.dumps, entry)

    def bench_decode_single_message(self, benchmark):
        raw = '{"role": "user", "content": "What is the status of the deployment?", "ts": "2025-01-01T10:00:00"}'
        benchmark(json.loads, raw)

    def bench_decode_batch_50(self, benchmark):
        raw_items = [
            json.dumps({"role": "user" if i % 2 == 0 else "assistant", "content": f"message {i}", "ts": "2025-01-01T00:00:00"})
            for i in range(50)
        ]
        benchmark(lambda items: [json.loads(item) for item in items], raw_items)


# ---------------------------------------------------------------------------
# BenchRetrievalPipelineAsync — retrieve() with mocked I/O
# ---------------------------------------------------------------------------

class BenchRetrievalPipelineAsync:
    def bench_retrieve_short_term_only(self, benchmark, agent_id):
        """Retrieve with mocked short-term Redis, no embeddings."""
        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        pipeline._stm.get_all = AsyncMock(
            return_value={f"key_{i}": f"value_{i}" for i in range(5)}
        )
        pipeline._stm.get_messages = AsyncMock(
            return_value=[{"role": "user", "content": f"msg {i}"} for i in range(10)]
        )
        pipeline._episodic.search = AsyncMock(return_value=[])

        def _run():
            run_async(pipeline.retrieve(query="test query", include_episodic=False))

        benchmark(_run)

    def bench_retrieve_with_episodic_results(self, benchmark, agent_id):
        """Retrieve with mocked episodic search returning 20 results."""
        pipeline = MemoryRetrievalPipeline(agent_id=agent_id)
        pipeline._stm.get_all = AsyncMock(return_value={})
        pipeline._stm.get_messages = AsyncMock(return_value=[])
        episodic_mem_results = [
            MemoryResult(source="episodic", content=f"chunk {i}", score=round(0.9 - i * 0.01, 2))
            for i in range(20)
        ]
        pipeline._retrieve_episodic = AsyncMock(return_value=episodic_mem_results)
        embedding = [0.1] * 384

        def _run():
            run_async(pipeline.retrieve(query="test", embedding=embedding, include_short_term=False))

        benchmark(_run)
