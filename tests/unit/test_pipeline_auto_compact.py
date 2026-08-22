"""Tests for CognitivePipeline's auto-compaction wiring (round 5 gap
analysis P2, 2026-08-21).

ConversationCompactor.maybe_compact() previously had zero real call sites
outside its own module and test file, despite its own docstring claiming
it's "called by the agent pipeline after every turn." These tests cover
only the new wiring — see test_memory_compactor.py for
ConversationCompactor's own behavior in isolation.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.channels.base import InboundMessage
from neuralcleave.memory.retrieval import RetrievalContext


class _RecordingRouter:
    def __init__(self, answer: str = "final answer"):
        self._answer = answer

    async def generate(self, prompt, *, task_type="general", system=None, session_id=None, **_kwargs):
        from neuralcleave.models.router import GenerationResult

        if task_type == "intent_extraction":
            return GenerationResult(text="chat", model="m", provider="p")
        return GenerationResult(text=self._answer, model="m", provider="p")

    async def generate_stream(self, prompt, *, task_type="general", system=None, session_id=None, **_kwargs):
        from neuralcleave.models.router import StreamChunk

        yield StreamChunk(text=self._answer, model="m", provider="p")
        yield StreamChunk(done=True, model="m", provider="p", usage={})


def _memory() -> MagicMock:
    memory = MagicMock()
    ctx = RetrievalContext(results=[], token_estimate=0)
    memory.retrieve = AsyncMock(return_value=ctx)
    memory.store_short_term = AsyncMock()
    memory.store_semantic = AsyncMock()
    return memory


def _session() -> MagicMock:
    session = MagicMock()
    session.session_id = "s1"
    session.turn_count = 1
    session.build_prompt.return_value = ""
    return session


def _msg() -> InboundMessage:
    import time

    return InboundMessage(channel="telegram", sender_id="u", sender_name="User", text="hi", timestamp=time.time())


async def _drain_background_tasks() -> None:
    """Fire-and-forget asyncio.create_task() calls need at least one event
    loop turn to actually run."""
    await asyncio.sleep(0)


class TestRunAutoCompact:
    @pytest.mark.asyncio
    async def test_triggers_when_long_term_is_given(self):
        long_term = MagicMock()
        pipeline = CognitivePipeline(
            router=_RecordingRouter(), memory=_memory(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
            long_term=long_term,
        )
        fake_compactor = MagicMock()
        fake_compactor.maybe_compact = AsyncMock(return_value=False)

        with patch("neuralcleave.memory.compactor.ConversationCompactor", return_value=fake_compactor) as ctor:
            await pipeline.run(_msg(), _session())
            await _drain_background_tasks()

        ctor.assert_called_once()
        fake_compactor.maybe_compact.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_when_no_long_term_given(self):
        pipeline = CognitivePipeline(
            router=_RecordingRouter(), memory=_memory(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        )

        with patch("neuralcleave.memory.compactor.ConversationCompactor") as ctor:
            await pipeline.run(_msg(), _session())
            await _drain_background_tasks()

        ctor.assert_not_called()

    @pytest.mark.asyncio
    async def test_failure_does_not_break_the_reply(self):
        """Compaction is a housekeeping optimization - it must never
        surface an exception to the caller or prevent a reply."""
        pipeline = CognitivePipeline(
            router=_RecordingRouter(answer="the actual reply"), memory=_memory(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
            long_term=MagicMock(),
        )

        with patch("neuralcleave.memory.compactor.ConversationCompactor", side_effect=RuntimeError("boom")):
            result = await pipeline.run(_msg(), _session())
            await _drain_background_tasks()

        assert result.response == "the actual reply"


class TestRunStreamAutoCompact:
    @pytest.mark.asyncio
    async def test_triggers_when_long_term_is_given(self):
        long_term = MagicMock()
        pipeline = CognitivePipeline(
            router=_RecordingRouter(), memory=_memory(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
            long_term=long_term,
        )
        fake_compactor = MagicMock()
        fake_compactor.maybe_compact = AsyncMock(return_value=False)

        with patch("neuralcleave.memory.compactor.ConversationCompactor", return_value=fake_compactor) as ctor:
            async for _ in pipeline.run_stream(_msg(), _session()):
                pass
            await _drain_background_tasks()

        ctor.assert_called_once()
        fake_compactor.maybe_compact.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_skipped_when_no_long_term_given(self):
        pipeline = CognitivePipeline(
            router=_RecordingRouter(), memory=_memory(),
            workspace=MagicMock(to_system_prompt=MagicMock(return_value="sys")),
        )

        with patch("neuralcleave.memory.compactor.ConversationCompactor") as ctor:
            async for _ in pipeline.run_stream(_msg(), _session()):
                pass
            await _drain_background_tasks()

        ctor.assert_not_called()
