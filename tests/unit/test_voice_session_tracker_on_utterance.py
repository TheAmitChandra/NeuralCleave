"""Tests for VoiceSessionTracker.on_utterance() core logic."""

from __future__ import annotations

from neuralcleave.voice.session_tracker import VoiceSessionTracker


class TestOnUtterance:
    def test_first_utterance_returns_false(self) -> None:
        tracker = VoiceSessionTracker()
        assert tracker.on_utterance() is False

    def test_increments_turn_count(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        assert tracker.turn_count == 1

    def test_multiple_utterances_increment_count(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        tracker.on_utterance()
        tracker.on_utterance()
        assert tracker.turn_count == 3

    def test_is_active_after_utterance(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=60.0)
        tracker.on_utterance()
        assert tracker.is_active is True

    def test_session_id_unchanged_within_timeout(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=60.0)
        tracker.on_utterance()
        id_before = tracker.session_id
        tracker.on_utterance()
        assert tracker.session_id == id_before

    def test_consecutive_utterance_returns_false(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=60.0)
        tracker.on_utterance()
        assert tracker.on_utterance() is False
