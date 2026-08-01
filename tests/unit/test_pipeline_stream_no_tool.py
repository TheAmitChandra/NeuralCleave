"""Tests for CognitivePipeline.run_stream() without tools registered."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline


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


def _make_pipeline(chunks) -> CognitivePipeline:
    router = MagicMock()
    router.generate_stream.return_value = _fake_stream(*chunks)
    router.generate = AsyncMock(return_value=MagicMock(text="intent", model="m", provider="p", usage={}))

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
        tool_registry=None,
    )


class TestPipelineStreamNoTool:
    @pytest.mark.asyncio
    async def test_yields_text_chunks(self) -> None:
        chunks = [
            _make_stream_chunk(text="Hello"),
            _make_stream_chunk(text=" world"),
            _make_stream_chunk(done=True),
        ]
        p = _make_pipeline(chunks)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "hi"

        results = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                results.append(c)

        text_chunks = [c for c in results if c.text and not c.done]
        assert len(text_chunks) >= 1

    @pytest.mark.asyncio
    async def test_yields_done_chunk_at_end(self) -> None:
        chunks = [
            _make_stream_chunk(text="Hi"),
            _make_stream_chunk(done=True),
        ]
        p = _make_pipeline(chunks)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "hello"

        results = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                results.append(c)

        assert results[-1].done is True

    @pytest.mark.asyncio
    async def test_done_chunk_has_pipeline_result(self) -> None:
        chunks = [
            _make_stream_chunk(text="Hi"),
            _make_stream_chunk(done=True),
        ]
        p = _make_pipeline(chunks)
        session = MagicMock()
        session.session_id = "s"
        session.build_prompt.return_value = ""
        session.turn_count = 1
        msg = MagicMock()
        msg.text = "hello"

        results = []
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for c in p.run_stream(msg, session):
                results.append(c)

        done_chunk = results[-1]
        assert done_chunk.result is not None
