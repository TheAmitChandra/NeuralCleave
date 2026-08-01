"""Tests for find_device() partial name matching."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict]) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (0, 1)
    return sd


_RAW = [
    {"name": "Built-in Microphone", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"name": "USB Audio Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
    {"name": "HDMI Output", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
]


class TestFindDevice:
    def test_finds_by_partial_name(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("microphone", kind="input")
        assert dev is not None
        assert dev.name == "Built-in Microphone"

    def test_case_insensitive_match(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("BUILT-IN", kind="input")
        assert dev is not None

    def test_returns_none_when_no_match(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("nonexistent_xyz", kind="input")
        assert dev is None

    def test_kind_output_restricts_to_outputs(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("USB Audio", kind="output")
        assert dev is not None
        assert "Speaker" in dev.name

    def test_kind_any_searches_all_devices(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("HDMI", kind="any")
        assert dev is not None

    def test_input_kind_does_not_match_output_device(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            dev = find_device("Speaker", kind="input")
        assert dev is None
