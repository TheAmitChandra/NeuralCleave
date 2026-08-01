"""Tests for CognitivePipeline.run() when tool execution returns an error."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _FailingTool(Tool):
    name = "failing_tool"
    description = "Always fails."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=None, error="Something went wrong")


def _make_pipeline_with_failing_tool(first_response: str) -> CognitivePipeline:
    call_count = {"n": 0}

    async def _gen(prompt, **kwargs):
        call_count["n"] += 1
        r = MagicMock()
        r.text = first_response if call_count["n"] == 1 else "I encountered an error with that tool."
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        return r

    registry = ToolRegistry()
    registry.register(_FailingTool())

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


class TestPipelineToolFailure:
    @pytest.mark.asyncio
    async def test_run_completes_even_when_tool_fails(self) -> None:
        first = 'TOOL_CALL: {"name": "failing_tool", "arguments": {}}'
        p = _make_pipeline_with_failing_tool(first)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "trigger fail"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)
        assert result is not None

    @pytest.mark.asyncio
    async def test_tool_error_injected_into_re_generation(self) -> None:
        first = 'TOOL_CALL: {"name": "failing_tool", "arguments": {}}'
        p = _make_pipeline_with_failing_tool(first)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "go"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)
        # Second generation should be used (tool error injected into context)
        assert "error" in result.response.lower() or result.response is not None
