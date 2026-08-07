"""Tests that PipelineResult.tool_steps is populated correctly by run()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes text."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


def _make_pipeline(responses: list[str], with_tools: bool = True) -> CognitivePipeline:
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

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()

    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "sys"

    registry = None
    if with_tools:
        registry = ToolRegistry()
        registry.register(_EchoTool())

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=memory,
        workspace=workspace,
        tool_registry=registry,
    )


def _make_msg(text: str = "hello") -> MagicMock:
    m = MagicMock()
    m.text = text
    return m


def _make_session() -> MagicMock:
    s = MagicMock()
    s.session_id = "sid"
    s.build_prompt.return_value = ""
    s.turn_count = 1
    return s


class TestToolStepsInResult:
    @pytest.mark.asyncio
    async def test_tool_steps_is_zero_when_no_tool_call(self) -> None:
        p = _make_pipeline(["plain text response"])
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_msg(), _make_session())
        assert result.tool_steps == 0

    @pytest.mark.asyncio
    async def test_tool_steps_is_zero_when_no_registry(self) -> None:
        p = _make_pipeline(["plain text response"], with_tools=False)
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_msg(), _make_session())
        assert result.tool_steps == 0

    @pytest.mark.asyncio
    async def test_tool_steps_is_one_after_single_tool_call(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hi"}}'
        p = _make_pipeline([first, "final"])
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_msg(), _make_session())
        assert result.tool_steps == 1

    @pytest.mark.asyncio
    async def test_tool_steps_is_two_after_two_step_chain(self) -> None:
        step1 = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "a"}}'
        step2 = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "b"}}'
        p = _make_pipeline([step1, step2, "done"])
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(_make_msg(), _make_session())
        assert result.tool_steps == 2
