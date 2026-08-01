"""Tests for list_input_devices() and list_output_devices() filtering."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict]) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (0, 1)
    return sd


_RAW = [
    {"name": "Mic Only", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"name": "Speaker Only", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
    {"name": "Duplex", "max_input_channels": 1, "max_output_channels": 1, "default_samplerate": 44100.0},
]


class TestListInputOutputDevices:
    def test_list_input_excludes_output_only(self) -> None:
        from neuralcleave.voice.device_manager import list_input_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            inputs = list_input_devices()
        names = [d.name for d in inputs]
        assert "Speaker Only" not in names

    def test_list_input_includes_duplex(self) -> None:
        from neuralcleave.voice.device_manager import list_input_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            inputs = list_input_devices()
        names = [d.name for d in inputs]
        assert "Duplex" in names

    def test_list_output_excludes_input_only(self) -> None:
        from neuralcleave.voice.device_manager import list_output_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            outputs = list_output_devices()
        names = [d.name for d in outputs]
        assert "Mic Only" not in names

    def test_list_output_includes_duplex(self) -> None:
        from neuralcleave.voice.device_manager import list_output_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            outputs = list_output_devices()
        names = [d.name for d in outputs]
        assert "Duplex" in names

    def test_is_input_property(self) -> None:
        from neuralcleave.voice.device_manager import list_input_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            inputs = list_input_devices()
        assert all(d.is_input for d in inputs)

    def test_is_output_property(self) -> None:
        from neuralcleave.voice.device_manager import list_output_devices

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            outputs = list_output_devices()
        assert all(d.is_output for d in outputs)
