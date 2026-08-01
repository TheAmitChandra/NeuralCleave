"""Tests for GET /voice/devices route."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient


def _make_client(runtime=None):
    from fastapi import FastAPI

    from neuralcleave.gateway.routes import router, set_runtime

    app = FastAPI()
    app.include_router(router)
    set_runtime(runtime)
    return TestClient(app)


class TestVoiceDevicesRoute:
    def test_returns_200(self) -> None:
        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client()
            resp = client.get("/api/v1/voice/devices")
        assert resp.status_code == 200

    def test_has_input_key(self) -> None:
        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client()
            data = client.get("/api/v1/voice/devices").json()
        assert "input" in data

    def test_has_output_key(self) -> None:
        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client()
            data = client.get("/api/v1/voice/devices").json()
        assert "output" in data

    def test_has_active_key(self) -> None:
        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client()
            data = client.get("/api/v1/voice/devices").json()
        assert "active" in data

    def test_active_reflects_runtime_devices(self) -> None:

        rt = MagicMock()
        rt._input_device = "Headset Mic"
        rt._output_device = None

        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client(runtime=rt)
            data = client.get("/api/v1/voice/devices").json()
        assert data["active"]["input_device"] == "Headset Mic"
        assert data["active"]["output_device"] is None

    def test_device_entries_have_expected_fields(self) -> None:
        from neuralcleave.voice.device_manager import AudioDevice

        dev = AudioDevice(
            index=0, name="Test Mic", max_input_channels=2, max_output_channels=0,
            default_sample_rate=44100.0, is_default_input=True, is_default_output=False,
        )
        with patch("neuralcleave.voice.device_manager.list_input_devices", return_value=[dev]), \
             patch("neuralcleave.voice.device_manager.list_output_devices", return_value=[]):
            client = _make_client()
            data = client.get("/api/v1/voice/devices").json()
        entry = data["input"][0]
        assert "index" in entry
        assert "name" in entry
        assert "channels" in entry
        assert "is_default" in entry
