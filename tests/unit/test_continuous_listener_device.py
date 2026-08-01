"""Tests for device param and set_device() on ContinuousVoiceListener."""

from __future__ import annotations

from unittest.mock import MagicMock


def _make_listener(device=None):
    from neuralcleave.voice.continuous import ContinuousVoiceListener

    stt = MagicMock()
    return ContinuousVoiceListener(stt, device=device)


class TestContinuousListenerDevice:
    def test_default_device_is_none(self) -> None:
        listener = _make_listener()
        assert listener._device is None

    def test_device_stored_on_init(self) -> None:
        listener = _make_listener(device=3)
        assert listener._device == 3

    def test_device_string_stored(self) -> None:
        listener = _make_listener(device="USB Mic")
        assert listener._device == "USB Mic"

    def test_set_device_updates_value(self) -> None:
        listener = _make_listener()
        listener.set_device(5)
        assert listener._device == 5

    def test_set_device_none_clears(self) -> None:
        listener = _make_listener(device=2)
        listener.set_device(None)
        assert listener._device is None

    def test_set_device_string(self) -> None:
        listener = _make_listener()
        listener.set_device("Built-in Microphone")
        assert listener._device == "Built-in Microphone"
