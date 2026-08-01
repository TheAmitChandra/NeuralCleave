"""Tests for CognitivePipeline.run() executing a tool and re-generating."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Returns the input unchanged."
    parameters = {"text": {"type": "str", "description": "Text to echo.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=f"echo: {text}")


def _make_pipeline_with_echo(first_response: str, second_response: str) -> CognitivePipeline:
    call_count = {"n": 0}

    async def _gen(prompt, **kwargs):
        call_count["n"] += 1
        result = MagicMock()
        result.text = first_response if call_count["n"] == 1 else second_response
        result.model = "test-model"
        result.provider = "test"
        result.usage = {}
        return result

    router = MagicMock()
    router.generate = _gen

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()

    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "You are helpful."

    registry = ToolRegistry()
    registry.register(_EchoTool())

    return CognitivePipeline(
        router=router,
        memory=memory,
        workspace=workspace,
        tool_registry=registry,
    )


class TestPipelineRunWithToolCall:
    @pytest.mark.asyncio
    async def test_tool_result_in_final_response(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hello"}}'
        second = "Here is the echo result."
        p = _make_pipeline_with_echo(first, second)
        session = MagicMock()
        session.session_id = "s1"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "test"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            result = await p.run(msg, session)
        assert result.response == second

    @pytest.mark.asyncio
    async def test_router_generate_called_twice_on_tool_call(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hi"}}'
        second = "Done."
        generate_calls = []

        async def _gen(prompt, **kwargs):
            generate_calls.append(prompt)
            r = MagicMock()
            r.text = first if len(generate_calls) == 1 else second
            r.model = "m"
            r.provider = "p"
            r.usage = {}
            return r

        registry = ToolRegistry()
        registry.register(_EchoTool())

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
        msg.text = "echo hi"
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            await p.run(msg, session)
        assert len(generate_calls) == 2
