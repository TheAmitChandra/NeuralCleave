"""Tests for WakeWordDetector.pause(), resume(), and _paused guard."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.voice.wake_word import WakeWordDetector


def _make_detector(on_wake=None) -> WakeWordDetector:
    return WakeWordDetector(model="hey_jarvis", on_wake=on_wake)


class TestPauseResume:
    def test_not_paused_by_default(self) -> None:
        d = _make_detector()
        assert d._paused is False

    def test_pause_sets_flag(self) -> None:
        d = _make_detector()
        d.pause()
        assert d._paused is True

    def test_resume_clears_flag(self) -> None:
        d = _make_detector()
        d.pause()
        d.resume()
        assert d._paused is False

    def test_resume_without_pause_is_safe(self) -> None:
        d = _make_detector()
        d.resume()
        assert d._paused is False

    def test_pause_twice_is_idempotent(self) -> None:
        d = _make_detector()
        d.pause()
        d.pause()
        assert d._paused is True


class TestPauseSuppressesCallback:
    def test_paused_suppresses_on_wake(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d.pause()
        scores = {"hey_jarvis": 1.0}
        d._check_scores(scores)
        cb.assert_not_called()

    def test_not_paused_fires_on_wake(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d._last_detection = 0.0
        scores = {"hey_jarvis": 1.0}
        d._check_scores(scores)
        cb.assert_called_once()

    def test_resume_allows_callback_again(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d.pause()
        d.resume()
        d._last_detection = 0.0
        scores = {"hey_jarvis": 1.0}
        d._check_scores(scores)
        cb.assert_called_once()


class TestTriggerCount:
    def test_trigger_count_zero_initially(self) -> None:
        d = _make_detector()
        assert d.trigger_count == 0

    def test_trigger_count_increments_on_detection(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d._last_detection = 0.0
        d._check_scores({"hey_jarvis": 1.0})
        assert d.trigger_count == 1

    def test_trigger_count_not_incremented_when_paused(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d.pause()
        d._check_scores({"hey_jarvis": 1.0})
        assert d.trigger_count == 0

    def test_trigger_count_not_incremented_below_threshold(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        d._last_detection = 0.0
        d._check_scores({"hey_jarvis": 0.1})
        assert d.trigger_count == 0

    def test_trigger_count_increments_multiple_times(self) -> None:
        cb = MagicMock()
        d = _make_detector(on_wake=cb)
        for _ in range(3):
            d._last_detection = 0.0
            d._check_scores({"hey_jarvis": 1.0})
        assert d.trigger_count == 3
