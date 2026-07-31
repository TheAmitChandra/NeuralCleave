"""Tests for VoiceConfig.ptt_max_duration_s and TOML loading."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig, load_config


class TestPttMaxDurationConfig:
    def test_default_ptt_max_duration_s(self) -> None:
        cfg = VoiceConfig()
        assert cfg.ptt_max_duration_s == 30.0

    def test_custom_ptt_max_duration_s(self) -> None:
        cfg = VoiceConfig(ptt_max_duration_s=10.0)
        assert cfg.ptt_max_duration_s == 10.0

    def test_zero_ptt_max_duration_s_accepted(self) -> None:
        cfg = VoiceConfig(ptt_max_duration_s=0.0)
        assert cfg.ptt_max_duration_s == 0.0


class TestPttMaxDurationToml:
    def test_toml_ptt_max_duration_s_loaded(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nptt_max_duration_s = 60.0\n")
        cfg = load_config(str(f))
        assert cfg.voice.ptt_max_duration_s == 60.0

    def test_toml_ptt_max_duration_default_when_absent(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(f))
        assert cfg.voice.ptt_max_duration_s == 30.0

    def test_toml_ptt_max_duration_subinteger(self, tmp_path) -> None:
        f = tmp_path / "config.toml"
        f.write_text("[voice]\nptt_max_duration_s = 7.5\n")
        cfg = load_config(str(f))
        assert cfg.voice.ptt_max_duration_s == 7.5
