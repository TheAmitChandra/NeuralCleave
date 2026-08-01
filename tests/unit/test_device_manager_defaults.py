"""Tests for get_default_input() and get_default_output()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict], default_in: int, default_out: int) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (default_in, default_out)
    return sd


_RAW = [
    {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
]


class TestGetDefaults:
    def test_get_default_input_returns_device(self) -> None:
        from neuralcleave.voice.device_manager import get_default_input

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW, 0, 1)}):
            dev = get_default_input()
        assert dev is not None
        assert dev.name == "Mic"

    def test_get_default_output_returns_device(self) -> None:
        from neuralcleave.voice.device_manager import get_default_output

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW, 0, 1)}):
            dev = get_default_output()
        assert dev is not None
        assert dev.name == "Speaker"

    def test_get_default_input_none_when_no_match(self) -> None:
        from neuralcleave.voice.device_manager import get_default_input

        # default_in points to a non-input device
        raw = [
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw, 0, 0)}):
            dev = get_default_input()
        assert dev is None

    def test_get_default_output_none_when_no_match(self) -> None:
        from neuralcleave.voice.device_manager import get_default_output

        raw = [
            {"name": "Mic", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
        ]
        with patch.dict("sys.modules", {"sounddevice": _mock_sd(raw, 0, 0)}):
            dev = get_default_output()
        assert dev is None

    def test_get_default_input_none_without_sounddevice(self) -> None:
        import sys

        from neuralcleave.voice.device_manager import get_default_input

        saved = sys.modules.pop("sounddevice", None)
        try:
            sys.modules["sounddevice"] = None  # type: ignore[assignment]
            dev = get_default_input()
        finally:
            if saved is not None:
                sys.modules["sounddevice"] = saved
            else:
                sys.modules.pop("sounddevice", None)
        assert dev is None
