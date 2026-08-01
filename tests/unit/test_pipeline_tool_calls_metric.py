"""Tests that tool_calls_total is incremented when a tool is executed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.observability.metrics import REGISTRY
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _NopTool(Tool):
    name = "nop"
    description = "Does nothing."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output="ok")


def _make_pipeline_with_nop(first_response: str) -> CognitivePipeline:
    call_count = {"n": 0}

    async def _gen(prompt, **kwargs):
        call_count["n"] += 1
        r = MagicMock()
        r.text = first_response if call_count["n"] == 1 else "Done."
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        return r

    registry = ToolRegistry()
    registry.register(_NopTool())

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()
    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "sys"

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=memory,
        workspace=workspace,
        tool_registry=registry,
    )


class TestPipelineToolCallsMetric:
    @pytest.mark.asyncio
    async def test_metric_incremented_on_tool_execution(self) -> None:
        metric = REGISTRY.get("tool_calls_total")
        metric.reset()
        first = 'TOOL_CALL: {"name": "nop", "arguments": {}}'
        p = _make_pipeline_with_nop(first)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "do nothing"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            await p.run(msg, session)
        assert metric.get() == 1.0

    @pytest.mark.asyncio
    async def test_metric_not_incremented_when_no_tool_call(self) -> None:
        metric = REGISTRY.get("tool_calls_total")
        metric.reset()
        first = "Just a regular response."
        p = _make_pipeline_with_nop(first)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "hello"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            await p.run(msg, session)
        assert metric.get() == 0.0
