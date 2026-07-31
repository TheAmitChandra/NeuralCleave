"""Tests for VoiceSessionTracker.reset() explicit session restart."""

from __future__ import annotations

from neuralcleave.voice.session_tracker import VoiceSessionTracker


class TestVoiceSessionReset:
    def test_reset_returns_string(self) -> None:
        tracker = VoiceSessionTracker()
        result = tracker.reset()
        assert isinstance(result, str)

    def test_reset_returns_new_session_id(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        old_id = tracker.session_id
        new_id = tracker.reset()
        assert new_id != old_id

    def test_reset_updates_session_id_property(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        new_id = tracker.reset()
        assert tracker.session_id == new_id

    def test_reset_clears_turn_count(self) -> None:
        tracker = VoiceSessionTracker()
        tracker.on_utterance()
        tracker.on_utterance()
        tracker.reset()
        assert tracker.turn_count == 0

    def test_reset_deactivates_session(self) -> None:
        tracker = VoiceSessionTracker(idle_timeout_s=9999.0)
        tracker.on_utterance()
        tracker.reset()
        assert tracker.is_active is False

    def test_reset_without_prior_utterance(self) -> None:
        tracker = VoiceSessionTracker()
        new_id = tracker.reset()
        assert isinstance(new_id, str)
        assert tracker.turn_count == 0
