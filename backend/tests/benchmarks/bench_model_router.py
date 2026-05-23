"""Benchmarks for the model router hot paths.

Covers:
  - Routing table lookup (task_type → provider)
  - Provider client selection (_get_client)
  - Fallback chain construction
  - Routing with mocked provider (successful call)
  - Routing with mocked provider fallback (first provider fails)
  - generate_structured call with mocked Gemini
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.benchmarks.conftest import run_async
from app.core.model_router.router import (
    ModelRouter,
    _ROUTING_TABLE,
    _FALLBACK_ORDER,
)


# ---------------------------------------------------------------------------
# BenchRoutingTableLookup — pure dict lookups, zero I/O
# ---------------------------------------------------------------------------

class BenchRoutingTableLookup:
    def bench_lookup_known_task(self, benchmark):
        """Look up a known task type in the routing table."""
        benchmark(_ROUTING_TABLE.get, "complex_reasoning", "gemini_flash")

    def bench_lookup_unknown_task(self, benchmark):
        """Look up an unknown task type (defaults to gemini_flash)."""
        benchmark(_ROUTING_TABLE.get, "nonexistent_task", "gemini_flash")

    def bench_lookup_all_tasks(self, benchmark):
        """Iterate all task types in the routing table."""
        def _lookup_all():
            return {task: _ROUTING_TABLE.get(task, "gemini_flash") for task in _ROUTING_TABLE}
        benchmark(_lookup_all)

    def bench_fallback_order_copy(self, benchmark):
        """Build a fallback provider list starting from a given preferred provider."""
        preferred = "gemini_pro"
        benchmark(
            lambda: [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]
        )

    def bench_fallback_order_deepseek(self, benchmark):
        preferred = "deepseek_coder"
        benchmark(
            lambda: [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]
        )


# ---------------------------------------------------------------------------
# BenchRouterInit — object construction
# ---------------------------------------------------------------------------

class BenchRouterInit:
    def bench_router_init(self, benchmark):
        """Instantiate a new ModelRouter (creates 4 client stubs)."""
        benchmark(ModelRouter)


# ---------------------------------------------------------------------------
# BenchClientSelection — _get_client hot path
# ---------------------------------------------------------------------------

class BenchClientSelection:
    @pytest.fixture
    def router(self) -> ModelRouter:
        return ModelRouter()

    def bench_get_client_gemini_flash(self, benchmark, router):
        benchmark(router._get_client, "gemini_flash")

    def bench_get_client_gemini_pro(self, benchmark, router):
        benchmark(router._get_client, "gemini_pro")

    def bench_get_client_deepseek(self, benchmark, router):
        benchmark(router._get_client, "deepseek_coder")

    def bench_get_client_ollama(self, benchmark, router):
        benchmark(router._get_client, "ollama")


# ---------------------------------------------------------------------------
# BenchRouterGenerate — full routing with mocked LLM I/O
# ---------------------------------------------------------------------------

class BenchRouterGenerate:
    @pytest.fixture
    def mocked_router(self) -> ModelRouter:
        router = ModelRouter()
        response_text = "Mocked LLM response for benchmark."
        router._gemini_flash.generate = AsyncMock(return_value=response_text)
        router._gemini_pro.generate = AsyncMock(return_value=response_text)
        router._deepseek.generate = AsyncMock(return_value=response_text)
        router._ollama.generate = AsyncMock(return_value=response_text)
        return router

    def bench_generate_general_task(self, benchmark, mocked_router):
        """Route a general task — hits gemini_flash on first try."""
        def _run():
            run_async(mocked_router.generate("What is 2+2?", task_type="general"))
        benchmark(_run)

    def bench_generate_code_generation(self, benchmark, mocked_router):
        """Route a code_generation task — hits deepseek_coder on first try."""
        def _run():
            run_async(mocked_router.generate("Write a Python sort function", task_type="code_generation"))
        benchmark(_run)

    def bench_generate_complex_reasoning(self, benchmark, mocked_router):
        """Route a complex_reasoning task — hits gemini_pro on first try."""
        def _run():
            run_async(mocked_router.generate("Explain quantum entanglement", task_type="complex_reasoning"))
        benchmark(_run)

    def bench_generate_with_system_instruction(self, benchmark, mocked_router):
        """Generate with a system instruction — tests parameter passing overhead."""
        def _run():
            run_async(mocked_router.generate(
                "Summarise this document",
                task_type="summarization",
                system_instruction="You are a concise summarizer.",
            ))
        benchmark(_run)

    def bench_generate_fallback_first_fails(self, benchmark):
        """Benchmark routing when the preferred provider fails and fallback succeeds."""
        router = ModelRouter()
        router._gemini_flash.generate = AsyncMock(side_effect=RuntimeError("provider down"))
        router._gemini_pro.generate = AsyncMock(return_value="fallback response")
        router._deepseek.generate = AsyncMock(return_value="fallback response")
        router._ollama.generate = AsyncMock(return_value="fallback response")

        def _run():
            run_async(router.generate("Test prompt", task_type="general"))
        benchmark(_run)


# ---------------------------------------------------------------------------
# BenchStructuredGenerate — generate_structured with mocked Gemini
# ---------------------------------------------------------------------------

class BenchStructuredGenerate:
    @pytest.fixture
    def struct_router(self) -> ModelRouter:
        router = ModelRouter()
        router._gemini_flash.generate_structured = AsyncMock(
            return_value={"intent": "search", "confidence": 0.95}
        )
        return router

    def bench_generate_structured_simple(self, benchmark, struct_router):
        schema = {"type": "object", "properties": {"intent": {"type": "string"}}}

        def _run():
            run_async(struct_router.generate_structured(
                "Extract the intent from: find me a hotel",
                response_schema=schema,
                task_type="intent_extraction",
            ))
        benchmark(_run)

    def bench_generate_structured_complex_schema(self, benchmark, struct_router):
        schema = {
            "type": "object",
            "properties": {
                "intent": {"type": "string"},
                "entities": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number"},
                "requires_tools": {"type": "boolean"},
            },
        }

        def _run():
            run_async(struct_router.generate_structured(
                "Book a flight from NYC to London for tomorrow",
                response_schema=schema,
                task_type="intent_extraction",
            ))
        benchmark(_run)
