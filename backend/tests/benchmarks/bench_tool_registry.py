"""Benchmarks for the ToolRegistry — registration, risk scoring, and execution pipeline.

Run with:
    pytest backend/tests/benchmarks/bench_tool_registry.py --benchmark-only -v
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from app.core.tools.registry import (
    ToolCallRequest,
    ToolDefinition,
    ToolRegistry,
    calculate_risk_score,
    resolve_isolation_tier,
)
from tests.benchmarks.conftest import run_async

# ---------------------------------------------------------------------------
# Risk scoring — pure CPU, no I/O
# ---------------------------------------------------------------------------


class BenchRiskScoring:
    """Micro-benchmarks for the risk calculation hot path."""

    def bench_risk_low_tool(self, benchmark):
        tool = ToolDefinition(
            name="bench.low",
            description="Low-risk tool",
            permissions=["file_read"],
            risk_level="low",
        )
        benchmark(calculate_risk_score, tool)

    def bench_risk_high_tool(self, benchmark):
        tool = ToolDefinition(
            name="bench.high",
            description="High-risk tool",
            permissions=["shell_access", "file_write", "network.external"],
            risk_level="high",
        )
        benchmark(calculate_risk_score, tool)

    def bench_resolve_isolation_tier_low(self, benchmark):
        benchmark(resolve_isolation_tier, 15.0)

    def bench_resolve_isolation_tier_high(self, benchmark):
        benchmark(resolve_isolation_tier, 75.0)


# ---------------------------------------------------------------------------
# Registry operations
# ---------------------------------------------------------------------------


class BenchRegistryOperations:
    """Benchmarks for tool registration and lookup."""

    def bench_register_single_tool(self, benchmark):
        async def _stub(p: dict) -> dict:
            return {}

        def setup():
            return ToolRegistry(), None, None

        def run():
            registry = ToolRegistry()
            tool = ToolDefinition(
                name=f"bench.reg.{uuid.uuid4().hex[:8]}",
                description="Benchmark registration",
                permissions=["file_read"],
                risk_level="low",
            )
            registry.register(tool, _stub)

        benchmark(run)

    def bench_list_tools_10(self, benchmark, fresh_registry):
        benchmark(fresh_registry.list_tools)

    def bench_get_definition_hit(self, benchmark, fresh_registry):
        benchmark(fresh_registry.get_definition, "bench.file.read")

    def bench_get_definition_miss(self, benchmark, fresh_registry):
        benchmark(fresh_registry.get_definition, "nonexistent.tool")

    def bench_check_permissions_all_granted(self, benchmark, fresh_registry):
        tool = fresh_registry.get_definition("bench.file.read")
        benchmark(fresh_registry.check_permissions, tool, ["file_read", "file_write", "web_access"])

    def bench_check_permissions_denied(self, benchmark, fresh_registry):
        tool = fresh_registry.get_definition("bench.shell.execute")
        benchmark(fresh_registry.check_permissions, tool, ["file_read"])


# ---------------------------------------------------------------------------
# Execution pipeline — async hot path
# ---------------------------------------------------------------------------


class BenchExecutionPipeline:
    """Benchmarks for the full async ToolRegistry.execute pipeline."""

    def bench_execute_low_risk_tool(self, benchmark, fresh_registry):
        agent_id = uuid.uuid4()
        request = ToolCallRequest(
            tool_name="bench.file.read",
            agent_id=agent_id,
            parameters={"path": "/tmp/test.txt"},
        )

        def run():
            return run_async(fresh_registry.execute(request, agent_permissions=["file_read"]))

        benchmark(run)

    def bench_execute_medium_risk_tool(self, benchmark, fresh_registry):
        agent_id = uuid.uuid4()
        request = ToolCallRequest(
            tool_name="bench.file.write",
            agent_id=agent_id,
            parameters={"path": "/tmp/out.txt", "content": "hello"},
        )

        def run():
            return run_async(fresh_registry.execute(request, agent_permissions=["file_write"]))

        benchmark(run)

    def bench_execute_high_risk_requires_approval(self, benchmark, fresh_registry):
        """Critical-risk tools block early — measures short-circuit path."""
        agent_id = uuid.uuid4()
        request = ToolCallRequest(
            tool_name="bench.shell.execute",
            agent_id=agent_id,
            parameters={"command": "ls -la"},
        )

        def run():
            return run_async(fresh_registry.execute(request, agent_permissions=["shell_access"]))

        benchmark(run)

    def bench_execute_permission_denied(self, benchmark, fresh_registry):
        """Permission-denied path should be very fast (early return)."""
        agent_id = uuid.uuid4()
        request = ToolCallRequest(
            tool_name="bench.shell.execute",
            agent_id=agent_id,
            parameters={"command": "ls"},
        )

        def run():
            return run_async(
                fresh_registry.execute(request, agent_permissions=[])  # no permissions
            )

        benchmark(run)

    def bench_execute_unknown_tool(self, benchmark, fresh_registry):
        """Unknown-tool path exits in O(1) dict lookup."""
        agent_id = uuid.uuid4()
        request = ToolCallRequest(
            tool_name="does.not.exist",
            agent_id=agent_id,
            parameters={},
        )

        def run():
            return run_async(fresh_registry.execute(request))

        benchmark(run)

    def bench_concurrent_executions_10(self, benchmark, fresh_registry):
        """Simulates 10 concurrent low-risk tool calls."""
        agent_id = uuid.uuid4()
        requests = [
            ToolCallRequest(
                tool_name="bench.file.read",
                agent_id=agent_id,
                parameters={"path": f"/tmp/{i}.txt"},
            )
            for i in range(10)
        ]

        async def run_all():
            return await asyncio.gather(
                *[fresh_registry.execute(r, agent_permissions=["file_read"]) for r in requests]
            )

        def run():
            return run_async(run_all())

        benchmark(run)
