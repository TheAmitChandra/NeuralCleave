"""Tests that _run_tool_chain emits tool_chain_depth metric."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.observability.metrics import REGISTRY
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes input."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


def _make_pipeline(responses: list[str]) -> CognitivePipeline:
    call_count = [0]

    async def _gen(prompt, **kwargs):
        r = MagicMock()
        idx = min(call_count[0], len(responses) - 1)
        r.text = responses[idx]
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        call_count[0] += 1
        return r

    registry = ToolRegistry()
    registry.register(_EchoTool())

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=MagicMock(),
        workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        tool_registry=registry,
    )


class TestToolChainDepthMetric:
    @pytest.mark.asyncio
    async def test_metric_observed_for_single_step_chain(self) -> None:
        m = REGISTRY.get("tool_chain_depth")
        assert m is not None
        before = m.get_count()

        p = _make_pipeline(["final"])
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hi"}}'
        await p._run_tool_chain(first, "user", "sys", "general")

        assert m.get_count() == before + 1

    @pytest.mark.asyncio
    async def test_metric_observed_value_equals_steps_taken(self) -> None:
        m = REGISTRY.get("tool_chain_depth")
        assert m is not None
        before_sum = m.get_sum()

        p = _make_pipeline([
            'TOOL_CALL: {"name": "echo", "arguments": {"text": "s2"}}',
            "done",
        ])
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "s1"}}'
        _, steps = await p._run_tool_chain(first, "user", "sys", "general")

        assert steps == 2
        assert m.get_sum() == before_sum + steps

    @pytest.mark.asyncio
    async def test_metric_not_observed_when_no_tool_called(self) -> None:
        m = REGISTRY.get("tool_chain_depth")
        assert m is not None
        before = m.get_count()

        p = _make_pipeline(["plain response"])
        await p._run_tool_chain("no tool here", "user", "sys", "general")

        assert m.get_count() == before  # no observation emitted
