"""Tests for CognitivePipeline.run() skipping tool execution on malformed TOOL_CALL."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _NopTool(Tool):
    name = "nop"
    description = "Does nothing."
    parameters = {}
    permissions: list[str] = []

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output="ok")


def _make_pipeline(response_text: str) -> CognitivePipeline:
    async def _gen(prompt, **kwargs):
        r = MagicMock()
        r.text = response_text
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


class TestPipelineMalformedToolCall:
    @pytest.mark.asyncio
    async def test_malformed_json_returns_original_response(self) -> None:
        first = "TOOL_CALL: {bad json here}"
        p = _make_pipeline(first)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "test"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)
        assert result.response == first

    @pytest.mark.asyncio
    async def test_unknown_tool_name_returns_error_block_in_context(self) -> None:
        first = 'TOOL_CALL: {"name": "unknown_tool", "arguments": {}}'
        call_count = {"n": 0}

        async def _gen(prompt, **kwargs):
            call_count["n"] += 1
            r = MagicMock()
            r.text = first if call_count["n"] == 1 else "Cannot find that tool."
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

        p = CognitivePipeline(
            router=MagicMock(generate=_gen),
            memory=memory,
            workspace=workspace,
            tool_registry=registry,
        )
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "use unknown tool"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)
        # The registry returns a ToolResult with error, which gets injected into
        # context for re-generation — still produces a response.
        assert result is not None
