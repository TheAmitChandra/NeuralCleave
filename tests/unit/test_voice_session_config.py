"""Tests for voice_session_idle_s config field."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig


class TestVoiceSessionConfig:
    def test_default_voice_session_idle_s(self) -> None:
        cfg = VoiceConfig()
        assert cfg.voice_session_idle_s == 300.0

    def test_custom_voice_session_idle_s(self) -> None:
        cfg = VoiceConfig(voice_session_idle_s=120.0)
        assert cfg.voice_session_idle_s == 120.0

    def test_voice_session_idle_s_is_float(self) -> None:
        cfg = VoiceConfig()
        assert isinstance(cfg.voice_session_idle_s, float)

    def test_zero_idle_s_allowed(self) -> None:
        cfg = VoiceConfig(voice_session_idle_s=0.0)
        assert cfg.voice_session_idle_s == 0.0

    def test_large_idle_s_stored(self) -> None:
        cfg = VoiceConfig(voice_session_idle_s=3600.0)
        assert cfg.voice_session_idle_s == 3600.0

    def test_voice_session_idle_s_independent_of_other_fields(self) -> None:
        cfg = VoiceConfig(voice_session_idle_s=60.0, ptt_max_duration_s=30.0)
        assert cfg.voice_session_idle_s == 60.0
        assert cfg.ptt_max_duration_s == 30.0
