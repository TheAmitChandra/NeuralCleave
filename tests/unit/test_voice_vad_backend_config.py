"""Tests for VoiceConfig.vad_backend field and TOML loading."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig, load_config


class TestVoiceConfigVadBackend:
    def test_default_vad_backend(self) -> None:
        cfg = VoiceConfig()
        assert cfg.vad_backend == "energy"

    def test_custom_vad_backend(self) -> None:
        cfg = VoiceConfig(vad_backend="webrtcvad")
        assert cfg.vad_backend == "webrtcvad"

    def test_vad_backend_accepts_energy(self) -> None:
        cfg = VoiceConfig(vad_backend="energy")
        assert cfg.vad_backend == "energy"


class TestVoiceConfigVadBackendToml:
    def test_toml_vad_backend_loaded(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nvad_backend = 'webrtcvad'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_backend == "webrtcvad"

    def test_toml_vad_backend_default_when_absent(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_backend == "energy"

    def test_toml_vad_backend_energy_explicit(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nvad_backend = 'energy'\n")
        cfg = load_config(str(f))
        assert cfg.voice.vad_backend == "energy"
