"""Tests for default_sample_rate field on AudioDevice."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict]) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (0, 1)
    return sd


class TestAudioDeviceSampleRate:
    def test_sample_rate_preserved(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [{"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000.0}]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            devices = list_devices()
        assert devices[0].default_sample_rate == 48000.0

    def test_missing_samplerate_defaults_to_44100(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [{"name": "Mic", "max_input_channels": 1, "max_output_channels": 0}]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            devices = list_devices()
        assert devices[0].default_sample_rate == 44100.0

    def test_missing_channels_default_zero(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [{"name": "Unknown", "default_samplerate": 44100.0}]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            devices = list_devices()
        assert devices[0].max_input_channels == 0
        assert devices[0].max_output_channels == 0
