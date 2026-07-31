"""Tests for VoiceSessionTracker initialisation and basic properties."""

from __future__ import annotations

import time

from neuralcleave.voice.session_tracker import VoiceSessionTracker


class TestVoiceSessionTrackerInit:
    def test_session_id_is_string(self) -> None:
        tracker = VoiceSessionTracker()
        assert isinstance(tracker.session_id, str)

    def test_session_id_nonempty(self) -> None:
        tracker = VoiceSessionTracker()
        assert len(tracker.session_id) > 0

    def test_turn_count_starts_at_zero(self) -> None:
        tracker = VoiceSessionTracker()
        assert tracker.turn_count == 0

    def test_idle_seconds_zero_before_any_utterance(self) -> None:
        tracker = VoiceSessionTracker()
        assert tracker.idle_seconds == 0.0

    def test_is_active_false_before_any_utterance(self) -> None:
        tracker = VoiceSessionTracker()
        assert tracker.is_active is False

    def test_idle_timeout_s_stored(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=120.0)
        assert tracker.idle_timeout_s == 120.0

    def test_started_at_is_recent(self) -> None:
        before = time.time()
        tracker = VoiceSessionTracker()
        assert tracker.started_at >= before
