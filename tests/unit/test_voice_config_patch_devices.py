"""Tests for input_device and output_device in PATCH /voice/config."""

from __future__ import annotations

from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client(runtime=None):
    from neuralcleave.gateway.routes import router, set_runtime

    app = FastAPI()
    app.include_router(router)
    set_runtime(runtime)
    return TestClient(app)


class TestVoiceConfigPatchDevices:
    def test_patch_input_device_calls_set_input_device(self) -> None:
        rt = MagicMock()
        client = _make_client(runtime=rt)
        client.patch("/api/v1/voice/config", json={"input_device": "USB Mic"})
        rt.set_input_device.assert_called_once_with("USB Mic")

    def test_patch_output_device_calls_set_output_device(self) -> None:
        rt = MagicMock()
        client = _make_client(runtime=rt)
        client.patch("/api/v1/voice/config", json={"output_device": "HDMI Out"})
        rt.set_output_device.assert_called_once_with("HDMI Out")

    def test_input_device_in_updated_fields(self) -> None:
        rt = MagicMock()
        rt._input_device = "USB Mic"
        rt._output_device = None
        client = _make_client(runtime=rt)
        resp = client.patch("/api/v1/voice/config", json={"input_device": "USB Mic"})
        assert "input_device" in resp.json()["updated_fields"]

    def test_output_device_in_updated_fields(self) -> None:
        rt = MagicMock()
        rt._input_device = None
        rt._output_device = "HDMI Out"
        client = _make_client(runtime=rt)
        resp = client.patch("/api/v1/voice/config", json={"output_device": "HDMI Out"})
        assert "output_device" in resp.json()["updated_fields"]

    def test_response_includes_active_devices(self) -> None:
        rt = MagicMock()
        rt._input_device = "Mic X"
        rt._output_device = "Speaker Y"
        client = _make_client(runtime=rt)
        resp = client.patch("/api/v1/voice/config", json={"input_device": "Mic X"})
        data = resp.json()
        assert "input_device" in data
        assert "output_device" in data

    def test_empty_body_does_not_call_set_input_device(self) -> None:
        rt = MagicMock()
        client = _make_client(runtime=rt)
        client.patch("/api/v1/voice/config", json={})
        rt.set_input_device.assert_not_called()
