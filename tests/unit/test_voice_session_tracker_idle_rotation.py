"""Tests for VoiceSessionTracker auto-rotation on idle timeout."""

from __future__ import annotations

import time
from unittest.mock import patch

from neuralcleave.voice.session_tracker import VoiceSessionTracker


def _make_tracker(idle_timeout_s: float = 1.0) -> VoiceSessionTracker:
    return VoiceSessionTracker(idle_timeout_s=idle_timeout_s)


class TestIdleRotation:
    def test_returns_true_after_idle_timeout(self) -> None:
        tracker = _make_tracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        result = tracker.on_utterance()
        assert result is True

    def test_session_id_changes_after_rotation(self) -> None:
        tracker = _make_tracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        id_before = tracker.session_id
        tracker.on_utterance()
        assert tracker.session_id != id_before

    def test_turn_count_resets_to_one_after_rotation(self) -> None:
        tracker = _make_tracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        tracker.on_utterance()
        tracker.on_utterance()
        assert tracker.turn_count == 1

    def test_no_rotation_within_timeout(self) -> None:
        tracker = _make_tracker(idle_timeout_s=9999.0)
        tracker.on_utterance()
        id_before = tracker.session_id
        tracker.on_utterance()
        assert tracker.session_id == id_before

    def test_is_active_false_after_timeout(self) -> None:
        tracker = _make_tracker(idle_timeout_s=0.0)
        tracker.on_utterance()
        assert tracker.is_active is False

    def test_idle_seconds_positive_after_utterance(self) -> None:
        tracker = _make_tracker()
        tracker.on_utterance()
        assert tracker.idle_seconds >= 0.0
