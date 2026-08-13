"""Tests proving run_stream() streams live when tools are registered but the
turn doesn't call one — the common case even in a tool-enabled session.

Before this change, ANY turn streamed with tool_registry set was fully
buffered and flushed as a single chunk only after a no-op _run_tool_chain
pass (see test_pipeline_stream_with_tool.py / test_pipeline_stream_tool_chain.py
for the TOOL_CALL-detected behaviour, which these tests do not change).
"""

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


def _make_pipeline(stream_chunks) -> CognitivePipeline:
    router = MagicMock()
    router.generate_stream.return_value = _fake_stream(*stream_chunks)
    router.generate = AsyncMock(return_value=MagicMock(text="unused", model="m", provider="p", usage={}))

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

    return CognitivePipeline(router=router, memory=memory, workspace=workspace, tool_registry=registry)


def _session() -> MagicMock:
    s = MagicMock()
    s.session_id = "s"
    s.build_prompt.return_value = ""
    s.turn_count = 1
    return s


def _msg() -> MagicMock:
    m = MagicMock()
    m.text = "hi"
    return m


class TestLiveStreamingWithoutToolCall:
    @pytest.mark.asyncio
    async def test_multiple_plain_text_chunks_stream_individually(self) -> None:
        """Each router chunk must reach the caller as its own PipelineStreamChunk
        (proving real streaming), not collapsed into one final flush."""
        p = _make_pipeline(
            [
                _make_stream_chunk(text="Hel"),
                _make_stream_chunk(text="lo "),
                _make_stream_chunk(text="there"),
                _make_stream_chunk(done=True),
            ]
        )
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            chunks = [c async for c in p.run_stream(_msg(), _session())]

        text_chunks = [c.text for c in chunks if c.text and not c.done]
        assert text_chunks == ["Hel", "lo ", "there"]

    @pytest.mark.asyncio
    async def test_final_assembled_response_is_correct(self) -> None:
        p = _make_pipeline(
            [_make_stream_chunk(text="Hello"), _make_stream_chunk(text=" world"), _make_stream_chunk(done=True)]
        )
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            chunks = [c async for c in p.run_stream(_msg(), _session())]

        assert chunks[-1].result.response == "Hello world"

    @pytest.mark.asyncio
    async def test_ambiguous_prefix_flushed_at_stream_end(self) -> None:
        """"TOO" is a genuine prefix of the marker (still ambiguous when the
        chunk arrives) but the stream ends before it resolves either way —
        it must still reach the caller exactly once, via the post-loop flush,
        not be dropped."""
        p = _make_pipeline([_make_stream_chunk(text="TOO"), _make_stream_chunk(done=True)])
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            chunks = [c async for c in p.run_stream(_msg(), _session())]

        text_chunks = [c.text for c in chunks if c.text and not c.done]
        assert text_chunks == ["TOO"]


class TestPreambleBeforeToolCallStillStreamsLive:
    @pytest.mark.asyncio
    async def test_completed_line_before_marker_streams_before_tool_result(self) -> None:
        """A line that completes (ends in \\n) before any TOOL_CALL marker
        appears must be yielded as soon as it's known-safe, arriving before
        the tool's result — not held back until the whole generation
        (including the tool call) finishes, and never containing the raw
        marker text."""
        p = _make_pipeline(
            [
                _make_stream_chunk(text="Let me check that.\n"),
                _make_stream_chunk(text='TOOL_CALL: {"name": "echo", "arguments": {"text": "x"}}'),
                _make_stream_chunk(done=True),
            ]
        )
        seen_before_done = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(_msg(), _session()):
                if c.text and not c.done:
                    seen_before_done.append(c.text)

        assert seen_before_done[0] == "Let me check that.\n"
        assert not any("TOOL_CALL:" in t for t in seen_before_done)
