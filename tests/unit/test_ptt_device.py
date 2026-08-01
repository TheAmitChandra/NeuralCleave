"""Tests for device param on PushToTalkRecorder."""

from __future__ import annotations

from neuralcleave.voice.ptt import PushToTalkRecorder


class TestPTTDevice:
    def test_default_device_none(self) -> None:
        ptt = PushToTalkRecorder()
        assert ptt._device is None

    def test_device_stored_on_init(self) -> None:
        ptt = PushToTalkRecorder(device=1)
        assert ptt._device == 1

    def test_device_string_stored(self) -> None:
        ptt = PushToTalkRecorder(device="Headset Mic")
        assert ptt._device == "Headset Mic"

    def test_device_independent_of_sample_rate(self) -> None:
        ptt = PushToTalkRecorder(sample_rate=44100, device=2)
        assert ptt._device == 2
        assert ptt._sample_rate == 44100
