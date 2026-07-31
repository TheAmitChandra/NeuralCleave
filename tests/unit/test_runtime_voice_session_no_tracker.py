"""Tests for graceful behavior when VoiceSessionTracker is not configured."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), voice_session=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeNoTracker:
    def test_voice_session_reset_returns_none(self) -> None:
        rt = _make_runtime()
        assert rt.voice_session_reset() is None

    def test_get_voice_session_info_returns_none(self) -> None:
        rt = _make_runtime()
        assert rt.get_voice_session_info() is None

    @pytest.mark.asyncio
    async def test_transcription_succeeds_without_tracker(self) -> None:
        rt = _make_runtime()

        async def _fake_stream(*a, **kw):
            return
            yield

        with patch.object(rt, "process_inbound_text_stream", side_effect=_fake_stream):
            await rt._on_voice_transcription("test")

    def test_voice_session_field_is_none(self) -> None:
        rt = _make_runtime()
        assert rt._voice_session is None

    def test_voice_session_field_set_when_passed(self) -> None:
        tracker = MagicMock()
        rt = _make_runtime(voice_session=tracker)
        assert rt._voice_session is tracker
