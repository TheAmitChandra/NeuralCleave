"""Tests for auto-rotation metric increment when idle timeout fires."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.voice.session_tracker import VoiceSessionTracker


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock())
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestAutoRotate:
    @pytest.mark.asyncio
    async def test_new_session_id_after_idle(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        id_before = tracker.session_id
        tracker.on_utterance()
        assert tracker.session_id != id_before

    @pytest.mark.asyncio
    async def test_sessions_metric_increments_on_auto_rotate(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        tracker = VoiceSessionTracker(idle_timeout_s=0.0)
        rt = _make_runtime(voice_session=tracker)
        tracker.on_utterance()
        before = REGISTRY.get("voice_sessions_total").get()

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("second utterance after idle")

        assert REGISTRY.get("voice_sessions_total").get() == before + 1.0

    @pytest.mark.asyncio
    async def test_turn_count_resets_after_auto_rotate(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        tracker.on_utterance()
        assert tracker.turn_count == 1

    def test_tracker_passed_to_runtime(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=60.0)
        rt = _make_runtime(voice_session=tracker)
        assert rt._voice_session is tracker

    def test_auto_rotate_preserves_idle_timeout(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=42.0)
        tracker.on_utterance()
        tracker.on_utterance()
        assert tracker.idle_timeout_s == 42.0
