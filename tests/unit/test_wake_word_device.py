"""Tests for device param on WakeWordDetector."""

from __future__ import annotations

from neuralcleave.voice.wake_word import WakeWordDetector


class TestWakeWordDevice:
    def test_default_device_none(self) -> None:
        det = WakeWordDetector()
        assert det._device is None

    def test_device_index_stored(self) -> None:
        det = WakeWordDetector(device=0)
        assert det._device == 0

    def test_device_string_stored(self) -> None:
        det = WakeWordDetector(device="USB Microphone")
        assert det._device == "USB Microphone"

    def test_device_independent_of_threshold(self) -> None:
        det = WakeWordDetector(threshold=0.7, device=3)
        assert det._device == 3
        assert det._threshold == 0.7
