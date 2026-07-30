"""Unit tests for VoiceConfig dataclass and config parsing."""

from __future__ import annotations

import pytest

from neuralcleave.config import VoiceConfig, load_config


# ---------------------------------------------------------------------------
# VoiceConfig defaults
# ---------------------------------------------------------------------------

class TestVoiceConfigDefaults:
    def test_stt_defaults_to_none(self) -> None:
        cfg = VoiceConfig()
        assert cfg.stt == "none"

    def test_tts_engine_defaults_to_none(self) -> None:
        cfg = VoiceConfig()
        assert cfg.tts_engine == "none"

    def test_stt_model_defaults_to_base(self) -> None:
        cfg = VoiceConfig()
        assert cfg.stt_model == "base"

    def test_stt_device_defaults_to_cpu(self) -> None:
        cfg = VoiceConfig()
        assert cfg.stt_device == "cpu"

    def test_language_defaults_to_empty(self) -> None:
        cfg = VoiceConfig()
        assert cfg.language == ""

    def test_wake_word_defaults_to_empty(self) -> None:
        cfg = VoiceConfig()
        assert cfg.wake_word == ""

    def test_wake_word_model_path_defaults_to_empty(self) -> None:
        cfg = VoiceConfig()
        assert cfg.wake_word_model_path == ""

    def test_wake_word_threshold_defaults_to_half(self) -> None:
        cfg = VoiceConfig()
        assert cfg.wake_word_threshold == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# VoiceConfig via load_config
# ---------------------------------------------------------------------------

class TestVoiceConfigLoading:
    def test_load_config_parses_voice_section(self, tmp_path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            "[voice]\n"
            'stt = "whisper"\n'
            'stt_model = "small"\n'
            'stt_device = "cuda"\n'
            'language = "fr"\n'
            'tts_engine = "kokoro"\n'
            'wake_word = "hey_jarvis"\n'
            "wake_word_threshold = 0.7\n"
        )
        cfg = load_config(str(cfg_file))
        assert cfg.voice.stt == "whisper"
        assert cfg.voice.stt_model == "small"
        assert cfg.voice.stt_device == "cuda"
        assert cfg.voice.language == "fr"
        assert cfg.voice.tts_engine == "kokoro"
        assert cfg.voice.wake_word == "hey_jarvis"
        assert cfg.voice.wake_word_threshold == pytest.approx(0.7)

    def test_load_config_no_voice_section_uses_defaults(self, tmp_path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text("[agent]\nname = 'NC'\n")
        cfg = load_config(str(cfg_file))
        assert cfg.voice.stt == "none"
        assert cfg.voice.wake_word == ""
        assert cfg.voice.wake_word_threshold == pytest.approx(0.5)

    def test_load_config_wake_word_model_path(self, tmp_path) -> None:
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text(
            "[voice]\n"
            'wake_word = "custom"\n'
            'wake_word_model_path = "/models/custom.tflite"\n'
        )
        cfg = load_config(str(cfg_file))
        assert cfg.voice.wake_word_model_path == "/models/custom.tflite"
