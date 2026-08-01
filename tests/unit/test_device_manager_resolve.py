"""Tests for resolve_device() — name/index/None → device index."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _mock_sd(devices: list[dict]) -> MagicMock:
    sd = MagicMock()
    sd.query_devices.return_value = devices
    sd.default.device = (0, 1)
    return sd


_RAW = [
    {"name": "Built-in Mic", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
    {"name": "USB Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 44100.0},
]


class TestResolveDevice:
    def test_none_returns_none(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        assert resolve_device(None) is None

    def test_empty_string_returns_none(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        assert resolve_device("") is None

    def test_int_returned_as_is(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        assert resolve_device(3) == 3

    def test_string_resolves_to_index(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            idx = resolve_device("Built-in", kind="input")
        assert idx == 0

    def test_unresolvable_name_returns_none(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            idx = resolve_device("does_not_exist_xyz", kind="input")
        assert idx is None

    def test_output_kind_resolves_output_device(self) -> None:
        from neuralcleave.voice.device_manager import resolve_device

        with patch.dict("sys.modules", {"sounddevice": _mock_sd(_RAW)}):
            idx = resolve_device("USB Speaker", kind="output")
        assert idx == 1
