"""Tests that the run_stream() path strips malformed TOOL_CALL markers.

The streaming path buffers the full generation when tools are registered,
then runs _run_tool_if_called().  When the JSON is malformed (model hallucinated
bad syntax), the pipeline must not yield raw TOOL_CALL text to the caller.
"""

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


def _make_stream_chunk(text="", done=False):
    chunk = MagicMock()
    chunk.text = text
    chunk.done = done
    chunk.error = None
    chunk.model = "m"
    chunk.provider = "p"
    chunk.usage = {}
    return chunk


async def _fake_stream(*chunks):
    for c in chunks:
        yield c


def _make_pipeline(stream_text: str) -> CognitivePipeline:
    stream_chunks = [_make_stream_chunk(text=stream_text), _make_stream_chunk(done=True)]

    async def _gen(prompt, **kwargs):
        r = MagicMock()
        r.text = "fallback response"
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        return r

    registry = ToolRegistry()
    registry.register(_NopTool())

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
        router=router, memory=memory, workspace=workspace, tool_registry=registry
    )


class TestPipelineStreamMalformedToolCall:
    @pytest.mark.asyncio
    async def test_malformed_json_not_yielded_to_caller(self) -> None:
        p = _make_pipeline("TOOL_CALL: {bad json here}")
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "test"

        all_text = ""
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                if c.text:
                    all_text += c.text

        assert "TOOL_CALL:" not in all_text
        assert all_text.strip()

    @pytest.mark.asyncio
    async def test_partial_tool_call_text_not_yielded(self) -> None:
        p = _make_pipeline("Here is some answer.\nTOOL_CALL: {incomplete")
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "test"

        all_text = ""
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                if c.text:
                    all_text += c.text

        assert "TOOL_CALL:" not in all_text

    @pytest.mark.asyncio
    async def test_plain_text_passes_through_unchanged(self) -> None:
        p = _make_pipeline("This is a plain text response with no tool call.")
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "hello"

        chunks = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                chunks.append(c)

        text_chunks = [c for c in chunks if c.text and not c.done]
        assert any("plain text response" in c.text for c in text_chunks)
