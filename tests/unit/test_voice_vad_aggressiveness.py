"""Tests for vad_aggressiveness config field, listener wiring, and REST exposure."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import fastapi
import pytest
from fastapi.testclient import TestClient

from neuralcleave.config import VoiceConfig
from neuralcleave.gateway.routes import router
from neuralcleave.voice.continuous import ContinuousVoiceListener
from neuralcleave.voice.vad import VoiceActivityDetector


class TestVoiceConfigAggressiveness:
    def test_default_vad_aggressiveness(self) -> None:
        cfg = VoiceConfig()
        assert cfg.vad_aggressiveness == 2

    def test_custom_vad_aggressiveness(self) -> None:
        cfg = VoiceConfig(vad_aggressiveness=3)
        assert cfg.vad_aggressiveness == 3

    def test_vad_aggressiveness_zero(self) -> None:
        cfg = VoiceConfig(vad_aggressiveness=0)
        assert cfg.vad_aggressiveness == 0


class TestVoiceActivityDetectorAggressivenessProperty:
    def test_default_aggressiveness(self) -> None:
        vad = VoiceActivityDetector()
        assert vad.aggressiveness == 2

    def test_custom_aggressiveness(self) -> None:
        vad = VoiceActivityDetector(aggressiveness=1)
        assert vad.aggressiveness == 1

    def test_aggressiveness_zero(self) -> None:
        vad = VoiceActivityDetector(aggressiveness=0)
        assert vad.aggressiveness == 0


class TestContinuousListenerAggressiveness:
    def test_default_vad_aggressiveness_forwarded(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt)
        assert listener._vad.aggressiveness == 2

    def test_custom_vad_aggressiveness_forwarded(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt, vad_aggressiveness=3)
        assert listener._vad.aggressiveness == 3

    def test_aggressiveness_zero_forwarded(self) -> None:
        stt = MagicMock()
        listener = ContinuousVoiceListener(stt, vad_aggressiveness=0)
        assert listener._vad.aggressiveness == 0


class TestVoiceConfigAggressivenessToml:
    def test_toml_vad_aggressiveness_loaded(self, tmp_path) -> None:
        from neuralcleave.config import load_config

        f = tmp_path / "config.toml"
        f.write_text("[voice]\nvad_aggressiveness = 1\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_aggressiveness == 1

    def test_toml_vad_aggressiveness_default_when_absent(self, tmp_path) -> None:
        from neuralcleave.config import load_config

        f = tmp_path / "config.toml"
        f.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_aggressiveness == 2


class TestGetVoiceConfigRouteAggressiveness:
    @pytest.fixture()
    def client(self):
        app = fastapi.FastAPI()
        app.include_router(router)
        return TestClient(app)

    def test_get_voice_config_includes_aggressiveness(self, client) -> None:
        rt = MagicMock()
        rt._continuous = MagicMock()
        rt._continuous._vad = MagicMock()
        rt._continuous._vad.backend = "energy"
        rt._continuous._vad.aggressiveness = 3
        rt._stt = None
        rt._tts = None

        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()

        assert data["vad_aggressiveness"] == 3

    def test_get_voice_config_aggressiveness_default_no_listener(self, client) -> None:
        rt = MagicMock()
        rt._continuous = None
        rt._stt = None
        rt._tts = None

        with patch("neuralcleave.gateway.routes.get_runtime", return_value=rt):
            data = client.get("/api/v1/voice/config").json()

        assert data["vad_aggressiveness"] == 2
