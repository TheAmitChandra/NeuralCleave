"""Tests for CognitivePipeline.run_stream() when a TOOL_CALL is detected."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes input."
    parameters = {"text": {"type": "str", "description": "Text.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=f"echo: {text}")


def _make_stream_chunk(text="", done=False, error=None):
    chunk = MagicMock()
    chunk.text = text
    chunk.done = done
    chunk.error = error
    chunk.model = "m"
    chunk.provider = "p"
    chunk.usage = {}
    return chunk


async def _fake_stream(*chunks):
    for c in chunks:
        yield c


def _make_pipeline_with_echo(first_stream_text: str, second_response: str) -> CognitivePipeline:
    stream_chunks = [
        _make_stream_chunk(text=first_stream_text),
        _make_stream_chunk(done=True),
    ]

    call_count = {"n": 0}

    async def _gen(prompt, **kwargs):
        call_count["n"] += 1
        r = MagicMock()
        r.text = second_response
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        return r

    registry = ToolRegistry()
    registry.register(_EchoTool())

    router = MagicMock()
    router.generate_stream.return_value = _fake_stream(*stream_chunks)
    router.generate = _gen

    memory = MagicMock()
    ctx = MagicMock()
    ctx.to_prompt_blocks.return_value = []
    ctx.token_estimate = 0
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()
    workspace = MagicMock()
    workspace.to_system_prompt.return_value = "sys"

    return CognitivePipeline(
        router=router,
        memory=memory,
        workspace=workspace,
        tool_registry=registry,
    )


class TestPipelineStreamWithTool:
    @pytest.mark.asyncio
    async def test_stream_yields_tool_result_response(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "hello"}}'
        second = "The echo result is: echo: hello"
        p = _make_pipeline_with_echo(first, second)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "echo hello"

        chunks = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                chunks.append(c)

        text_chunks = [c for c in chunks if c.text and not c.done]
        assert any(second in c.text for c in text_chunks)

    @pytest.mark.asyncio
    async def test_stream_done_chunk_has_result(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "test"}}'
        second = "Here is the result."
        p = _make_pipeline_with_echo(first, second)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "go"

        results = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                results.append(c)

        done_chunk = results[-1]
        assert done_chunk.done is True
        assert done_chunk.result is not None

    @pytest.mark.asyncio
    async def test_tool_call_marker_not_yielded_to_caller(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "x"}}'
        second = "Done."
        p = _make_pipeline_with_echo(first, second)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "go"

        all_text = ""
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                if c.text:
                    all_text += c.text

        # The raw TOOL_CALL: line should not appear in streamed output
        assert "TOOL_CALL:" not in all_text
