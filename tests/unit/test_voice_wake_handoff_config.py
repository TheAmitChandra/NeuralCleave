"""Tests for wake_handoff_duration_s in VoiceConfig and TOML loading."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig, load_config


class TestWakeHandoffDurationConfig:
    def test_default_wake_handoff_duration_s(self) -> None:
        cfg = VoiceConfig()
        assert cfg.wake_handoff_duration_s == 10.0

    def test_custom_wake_handoff_duration_s(self) -> None:
        cfg = VoiceConfig(wake_handoff_duration_s=5.0)
        assert cfg.wake_handoff_duration_s == 5.0

    def test_wake_handoff_duration_zero_allowed(self) -> None:
        cfg = VoiceConfig(wake_handoff_duration_s=0.0)
        assert cfg.wake_handoff_duration_s == 0.0


class TestWakeHandoffToml:
    def test_toml_wake_handoff_duration_s_loaded(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nwake_handoff_duration_s = 20.0\n")
        cfg = load_config(str(f))
        assert cfg.voice.wake_handoff_duration_s == 20.0

    def test_toml_wake_handoff_duration_default_when_absent(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(f))
        assert cfg.voice.wake_handoff_duration_s == 10.0

    def test_toml_wake_handoff_duration_subinteger(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nwake_handoff_duration_s = 2.5\n")
        cfg = load_config(str(f))
        assert cfg.voice.wake_handoff_duration_s == 2.5
