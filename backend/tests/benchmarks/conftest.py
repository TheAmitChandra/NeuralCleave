"""Benchmark conftest — shared fixtures and configuration.

Provides:
    async_benchmark  — helper that wraps async callables for sync benchmark harness
    fresh_registry   — isolated ToolRegistry instance with default tools
    mock_redis       — lightweight in-memory dict simulating Redis for memory benchmarks
"""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Awaitable, Callable

import pytest

from app.core.tools.registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Async benchmark helper
# ---------------------------------------------------------------------------

def run_async(coro: Awaitable) -> Any:
    """Run an awaitable in a fresh event loop (sync context for benchmark harness)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_registry() -> ToolRegistry:
    """Return a fresh ToolRegistry (not the global singleton) with default tools."""
    registry = ToolRegistry()  # new instance, not the singleton

    async def _stub(params: dict) -> dict:
        return {"ok": True, "params": params}

    default_tools = [
        ToolDefinition(
            name="bench.file.read",
            description="Benchmark: file read",
            permissions=["file_read"],
            risk_level="low",
        ),
        ToolDefinition(
            name="bench.file.write",
            description="Benchmark: file write",
            permissions=["file_write"],
            risk_level="medium",
            sandbox_required=True,
        ),
        ToolDefinition(
            name="bench.api.get",
            description="Benchmark: HTTP GET",
            permissions=["api_access"],
            risk_level="low",
        ),
        ToolDefinition(
            name="bench.shell.execute",
            description="Benchmark: shell exec",
            permissions=["shell_access"],
            risk_level="high",
            requires_approval=True,
            sandbox_required=True,
        ),
    ]
    for td in default_tools:
        registry.register(td, _stub)

    return registry
