"""Tests for on_utterance() wiring in AgentRuntime._on_voice_transcription."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), voice_session=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestVoiceSessionWiring:
    @pytest.mark.asyncio
    async def test_on_utterance_called_on_transcription(self) -> None:
        tracker = MagicMock()
        tracker.on_utterance.return_value = False
        rt = _make_runtime(voice_session=tracker)

        async def _fake_stream(*a, **kw):
            return
            yield  # make it an async generator

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("hello")

        tracker.on_utterance.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_error_when_tracker_is_none(self) -> None:
        rt = _make_runtime(voice_session=None)

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("hello")

    @pytest.mark.asyncio
    async def test_turns_metric_incremented(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        tracker = MagicMock()
        tracker.on_utterance.return_value = False
        rt = _make_runtime(voice_session=tracker)
        before = REGISTRY.get("voice_session_turns_total").get()

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("hi")

        assert REGISTRY.get("voice_session_turns_total").get() == before + 1.0

    @pytest.mark.asyncio
    async def test_sessions_metric_incremented_on_new_session(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        tracker = MagicMock()
        tracker.on_utterance.return_value = True
        rt = _make_runtime(voice_session=tracker)
        before = REGISTRY.get("voice_sessions_total").get()

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("new session")

        assert REGISTRY.get("voice_sessions_total").get() == before + 1.0

    @pytest.mark.asyncio
    async def test_sessions_metric_not_incremented_on_same_session(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        tracker = MagicMock()
        tracker.on_utterance.return_value = False
        rt = _make_runtime(voice_session=tracker)
        before = REGISTRY.get("voice_sessions_total").get()

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("same session")

        assert REGISTRY.get("voice_sessions_total").get() == before
