"""Tests for AudioDevice dataclass properties."""

from __future__ import annotations

from neuralcleave.voice.device_manager import AudioDevice


class TestAudioDeviceDataclass:
    def _make(self, *, in_ch: int = 0, out_ch: int = 0) -> AudioDevice:
        return AudioDevice(
            index=0,
            name="Test",
            max_input_channels=in_ch,
            max_output_channels=out_ch,
            default_sample_rate=44100.0,
            is_default_input=False,
            is_default_output=False,
        )

    def test_is_input_true_when_has_channels(self) -> None:
        dev = self._make(in_ch=2)
        assert dev.is_input is True

    def test_is_input_false_when_no_channels(self) -> None:
        dev = self._make(in_ch=0)
        assert dev.is_input is False

    def test_is_output_true_when_has_channels(self) -> None:
        dev = self._make(out_ch=1)
        assert dev.is_output is True

    def test_is_output_false_when_no_channels(self) -> None:
        dev = self._make(out_ch=0)
        assert dev.is_output is False

    def test_frozen_immutable(self) -> None:
        import pytest
        dev = self._make(in_ch=1)
        with pytest.raises((AttributeError, TypeError)):
            dev.name = "changed"  # type: ignore[misc]

    def test_equality_by_value(self) -> None:
        a = self._make(in_ch=1)
        b = self._make(in_ch=1)
        assert a == b
