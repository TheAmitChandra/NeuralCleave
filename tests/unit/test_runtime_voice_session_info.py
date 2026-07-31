"""Tests for AgentRuntime.get_voice_session_info()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), voice_session=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeVoiceSessionInfo:
    def test_returns_none_when_no_tracker(self) -> None:
        rt = _make_runtime(voice_session=None)
        assert rt.get_voice_session_info() is None

    def test_returns_dict_when_tracker_present(self) -> None:
        tracker = MagicMock()
        tracker.info.return_value = {"session_id": "abc", "turn_count": 3}
        rt = _make_runtime(voice_session=tracker)
        result = rt.get_voice_session_info()
        assert isinstance(result, dict)

    def test_calls_tracker_info(self) -> None:
        tracker = MagicMock()
        tracker.info.return_value = {}
        rt = _make_runtime(voice_session=tracker)
        rt.get_voice_session_info()
        tracker.info.assert_called_once()

    def test_returns_tracker_info_contents(self) -> None:
        info_dict = {"session_id": "xyz", "turn_count": 2, "is_active": True}
        tracker = MagicMock()
        tracker.info.return_value = info_dict
        rt = _make_runtime(voice_session=tracker)
        assert rt.get_voice_session_info() == info_dict

    def test_real_tracker_info_has_session_id(self) -> None:
        from neuralcleave.voice.session_tracker import VoiceSessionTracker

        tracker = VoiceSessionTracker()
        rt = _make_runtime(voice_session=tracker)
        info = rt.get_voice_session_info()
        assert "session_id" in info
