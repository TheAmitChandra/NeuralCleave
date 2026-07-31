"""Tests for VoiceSessionTracker.info() snapshot dict."""

from __future__ import annotations

from neuralcleave.voice.session_tracker import VoiceSessionTracker


class TestVoiceSessionInfo:
    def test_info_is_dict(self) -> None:
        tracker = VoiceSessionTracker()
        assert isinstance(tracker.info(), dict)

    def test_info_contains_session_id(self) -> None:
        tracker = VoiceSessionTracker()
        assert "session_id" in tracker.info()

    def test_info_session_id_matches_property(self) -> None:
        tracker = VoiceSessionTracker()
        assert tracker.info()["session_id"] == tracker.session_id

    def test_info_contains_turn_count(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        assert tracker.info()["turn_count"] == 1

    def test_info_contains_is_active(self) -> None:
        tracker = VoiceSessionTracker()
        assert "is_active" in tracker.info()

    def test_info_contains_idle_seconds(self) -> None:
        tracker = VoiceSessionTracker()
        assert "idle_seconds" in tracker.info()

    def test_info_contains_idle_timeout_s(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=120.0)
        assert tracker.info()["idle_timeout_s"] == 120.0
