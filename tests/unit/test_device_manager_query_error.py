"""Tests for graceful handling when sounddevice.query_devices() raises."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


class TestDeviceManagerQueryError:
    def test_list_devices_returns_empty_on_query_error(self) -> None:
        from neuralcleave.voice.device_manager import list_devices

        sd = MagicMock()
        sd.query_devices.side_effect = OSError("no audio hardware")
        with patch.dict("sys.modules", {"sounddevice": sd}):
            result = list_devices()
        assert result == []

    def test_find_device_returns_none_on_query_error(self) -> None:
        from neuralcleave.voice.device_manager import find_device

        sd = MagicMock()
        sd.query_devices.side_effect = OSError("no audio hardware")
        with patch.dict("sys.modules", {"sounddevice": sd}):
            result = find_device("anything")
        assert result is None

    def test_get_default_input_returns_none_on_error(self) -> None:
        from neuralcleave.voice.device_manager import get_default_input

        sd = MagicMock()
        sd.query_devices.side_effect = RuntimeError("driver error")
        with patch.dict("sys.modules", {"sounddevice": sd}):
            result = get_default_input()
        assert result is None
