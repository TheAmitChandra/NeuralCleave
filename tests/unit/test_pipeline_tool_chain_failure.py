"""Tests for _run_tool_chain behaviour when a tool call fails."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _BrokenTool(Tool):
    """Always returns an error ToolResult."""

    name = "broken"
    description = "Always fails."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=None, error="service unavailable")


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes text."
    parameters = {"text": {"type": "str", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


def _make_pipeline_with_tools(responses: list[str]) -> CognitivePipeline:
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
    registry.register(_BrokenTool())
    registry.register(_EchoTool())

    return CognitivePipeline(
        router=MagicMock(generate=_gen),
        memory=MagicMock(),
        workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
        tool_registry=registry,
    )


class TestToolChainToolFailure:
    @pytest.mark.asyncio
    async def test_chain_continues_after_tool_error(self) -> None:
        # broken tool returns error; chain still re-generates and continues
        p = _make_pipeline_with_tools(["final answer after error"])
        first = 'TOOL_CALL: {"name": "broken", "arguments": {}}'
        text, steps = await p._run_tool_chain(first, "user", "sys", "general")
        assert steps == 1
        assert text == "final answer after error"

    @pytest.mark.asyncio
    async def test_error_block_injected_into_context(self) -> None:
        received: list[str] = []

        async def _gen(prompt, **kwargs):
            received.append(prompt)
            r = MagicMock()
            r.text = "i see the error"
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            return r

        registry = ToolRegistry()
        registry.register(_BrokenTool())

        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
        )

        first = 'TOOL_CALL: {"name": "broken", "arguments": {}}'
        await p._run_tool_chain(first, "base prompt", "sys", "general")

        # The re-generation prompt must include the tool error block
        assert "[TOOL:broken ERROR]" in received[0]
        assert "service unavailable" in received[0]

    @pytest.mark.asyncio
    async def test_unknown_tool_error_block_in_context(self) -> None:
        received: list[str] = []

        async def _gen(prompt, **kwargs):
            received.append(prompt)
            r = MagicMock()
            r.text = "handled unknown"
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            return r

        registry = ToolRegistry()
        registry.register(_EchoTool())

        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=MagicMock(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="s")),
            tool_registry=registry,
        )

        first = 'TOOL_CALL: {"name": "nonexistent", "arguments": {}}'
        text, steps = await p._run_tool_chain(first, "base", "sys", "general")

        assert steps == 1
        assert "nonexistent" in received[0]  # error mentions unknown tool
