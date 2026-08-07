"""Tests for run_stream() multi-step tool chain behaviour."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _EchoTool(Tool):
    name = "echo"
    description = "Echoes input."
    parameters = {"text": {"type": "str", "description": "Input.", "required": True}}
    permissions: list[str] = []

    async def execute(self, text: str = "", **kwargs) -> ToolResult:
        return ToolResult(tool=self.name, output=text)


def _make_stream_chunk(text: str = "", done: bool = False):
    c = MagicMock()
    c.text = text
    c.done = done
    c.error = None
    c.model = "m"
    c.provider = "p"
    c.usage = {}
    return c


async def _fake_stream(*chunks):
    for c in chunks:
        yield c


def _make_pipeline(stream_text: str, generate_responses: list[str]) -> CognitivePipeline:
    """Stream *stream_text* from the first generation; subsequent calls use *generate_responses*."""
    call_count = [0]

    async def _gen(prompt, **kwargs):
        r = MagicMock()
        idx = min(call_count[0], len(generate_responses) - 1)
        r.text = generate_responses[idx]
        r.model = "m"
        r.provider = "p"
        r.usage = {}
        call_count[0] += 1
        return r

    registry = ToolRegistry()
    registry.register(_EchoTool())

    router = MagicMock()
    router.generate_stream.return_value = _fake_stream(
        _make_stream_chunk(text=stream_text),
        _make_stream_chunk(done=True),
    )
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


def _make_session() -> MagicMock:
    s = MagicMock()
    s.session_id = "sid"
    s.build_prompt.return_value = ""
    s.turn_count = 1
    return s


def _make_msg(text: str = "hi") -> MagicMock:
    m = MagicMock()
    m.text = text
    return m


class TestStreamToolChain:
    @pytest.mark.asyncio
    async def test_two_step_chain_final_text_reaches_caller(self) -> None:
        step1 = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "a"}}'
        step2 = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "b"}}'
        p = _make_pipeline(stream_text=step1, generate_responses=[step2, "all done"])

        all_text = ""
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for chunk in p.run_stream(_make_msg(), _make_session()):
                if chunk.text:
                    all_text += chunk.text

        assert "all done" in all_text
        assert "TOOL_CALL:" not in all_text

    @pytest.mark.asyncio
    async def test_stream_done_chunk_tool_steps_matches_chain_length(self) -> None:
        step1 = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "x"}}'
        p = _make_pipeline(stream_text=step1, generate_responses=["final"])

        done_chunk = None
        with patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")):
            async for chunk in p.run_stream(_make_msg(), _make_session()):
                if chunk.done:
                    done_chunk = chunk

        assert done_chunk is not None
        assert done_chunk.result is not None
        assert done_chunk.result.tool_steps == 1

    @pytest.mark.asyncio
    async def test_stream_uses_run_tool_chain_not_old_method(self) -> None:
        first = 'TOOL_CALL: {"name": "echo", "arguments": {"text": "y"}}'
        p = _make_pipeline(stream_text=first, generate_responses=["ok"])

        with (
            patch.object(p, "_extract_intent", new=AsyncMock(return_value="chat")),
            patch.object(
                p, "_run_tool_chain", new=AsyncMock(return_value=("ok", 1))
            ) as chain_mock,
        ):
            async for _ in p.run_stream(_make_msg(), _make_session()):
                pass

        chain_mock.assert_called_once()
