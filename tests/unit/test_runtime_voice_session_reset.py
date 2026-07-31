"""Tests for AgentRuntime.voice_session_reset()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), voice_session=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeVoiceSessionReset:
    def test_returns_none_when_no_tracker(self) -> None:
        rt = _make_runtime(voice_session=None)
        assert rt.voice_session_reset() is None

    def test_returns_string_when_tracker_present(self) -> None:
        tracker = MagicMock()
        tracker.reset.return_value = "new-uuid"
        rt = _make_runtime(voice_session=tracker)
        result = rt.voice_session_reset()
        assert isinstance(result, str)

    def test_calls_tracker_reset(self) -> None:
        tracker = MagicMock()
        tracker.reset.return_value = "some-id"
        rt = _make_runtime(voice_session=tracker)
        rt.voice_session_reset()
        tracker.reset.assert_called_once()

    def test_returns_tracker_session_id(self) -> None:
        tracker = MagicMock()
        tracker.reset.return_value = "abc-123"
        rt = _make_runtime(voice_session=tracker)
        assert rt.voice_session_reset() == "abc-123"

    def test_increments_sessions_metric(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        tracker = MagicMock()
        tracker.reset.return_value = "new-id"
        rt = _make_runtime(voice_session=tracker)
        before = REGISTRY.get("voice_sessions_total").get()
        rt.voice_session_reset()
        assert REGISTRY.get("voice_sessions_total").get() == before + 1.0

    def test_no_metric_increment_when_no_tracker(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        rt = _make_runtime(voice_session=None)
        before = REGISTRY.get("voice_sessions_total").get()
        rt.voice_session_reset()
        assert REGISTRY.get("voice_sessions_total").get() == before
