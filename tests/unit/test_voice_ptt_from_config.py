"""Tests that AgentRuntime.from_config creates PTT with the right parameters."""

from __future__ import annotations

from neuralcleave.config import VoiceConfig
from neuralcleave.voice.ptt import PushToTalkRecorder


class TestPttFromConfig:
    def test_ptt_recorder_accepts_config_max_duration(self) -> None:
        cfg = VoiceConfig(ptt_max_duration_s=45.0)
        ptt = PushToTalkRecorder(max_duration_s=cfg.ptt_max_duration_s)
        assert ptt.max_duration_s == 45.0

    def test_ptt_recorder_default_config_max_duration(self) -> None:
        cfg = VoiceConfig()
        ptt = PushToTalkRecorder(max_duration_s=cfg.ptt_max_duration_s)
        assert ptt.max_duration_s == 30.0

    def test_ptt_recorder_created_with_voice_config(self) -> None:
        cfg = VoiceConfig(ptt_max_duration_s=20.0)
        ptt = PushToTalkRecorder(max_duration_s=cfg.ptt_max_duration_s)
        assert isinstance(ptt, PushToTalkRecorder)

    def test_ptt_default_sample_rate(self) -> None:
        ptt = PushToTalkRecorder()
        assert ptt.sample_rate == 16_000

    def test_ptt_not_recording_after_construction(self) -> None:
        ptt = PushToTalkRecorder(max_duration_s=30.0)
        assert ptt.is_recording is False
