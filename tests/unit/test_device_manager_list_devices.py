"""Tests for device_manager.list_devices() with mocked sounddevice."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict], default_in: int = 0, default_out: int = 1) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (default_in, default_out)
    return sd


class TestListDevices:
    def test_returns_list(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [{"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0}]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            result = list_devices()
        assert isinstance(result, list)

    def test_device_count_matches(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [
            {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            result = list_devices()
        assert len(result) == 2

    def test_device_name_preserved(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [{"name": "USB Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000.0}]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            result = list_devices()
        assert result[0].name == "USB Mic"

    def test_device_index_assigned(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [
            {"name": "A", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "B", "max_input_channels": 0, "max_output_channels": 1, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw)}):
            devices = list_devices()
        assert devices[0].index == 0
        assert devices[1].index == 1

    def test_default_input_flagged(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 1, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw, default_in=0, default_out=1)}):
            devices = list_devices()
        assert devices[0].is_default_input is True
        assert devices[1].is_default_input is False

    def test_default_output_flagged(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        raw = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 1, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw, default_in=0, default_out=1)}):
            devices = list_devices()
        assert devices[1].is_default_output is True
        assert devices[0].is_default_output is False

    def test_empty_when_no_sounddevice(self) -> None:
        import sys

        from neuralcleave.voice.device_manager import list_devices

        saved = sys.modules.pop("sounddevice", None)
        try:
            sys.modules["sounddevice"] = None  # type: ignore[assignment]
            result = list_devices()
        finally:
            if saved is not None:
                sys.modules["sounddevice"] = saved
            else:
                sys.modules.pop("sounddevice", None)
        assert result == []
