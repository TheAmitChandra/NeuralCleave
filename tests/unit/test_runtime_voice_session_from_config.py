"""Tests for VoiceSessionTracker wiring in AgentRuntime.from_config()."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from neuralcleave.config import NeuralCleaveConfig
from neuralcleave.voice.session_tracker import VoiceSessionTracker


def _patched_from_config(voice_session_idle_s: float = 300.0):
    cfg = NeuralCleaveConfig()
    cfg.voice.voice_session_idle_s = voice_session_idle_s

    with (
        patch("neuralcleave.agent.runtime.ModelRouter"),
        patch("neuralcleave.agent.runtime.MemoryRetrievalPipeline"),
        patch("neuralcleave.agent.runtime.CognitivePipeline"),
        patch("neuralcleave.agent.runtime.SessionManager"),
        patch("neuralcleave.agent.runtime.LongTermMemory"),
        patch("neuralcleave.agent.runtime.WorkspaceLoader"),
        patch("neuralcleave.agent.runtime._build_adapters", return_value=[]),
    ):
        from neuralcleave.agent.runtime import AgentRuntime
        return AgentRuntime.from_config(cfg)


class TestFromConfigVoiceSession:
    def test_voice_session_tracker_created(self) -> None:
        rt = _patched_from_config()
        assert rt._voice_session is not None

    def test_voice_session_is_tracker_instance(self) -> None:
        rt = _patched_from_config()
        assert isinstance(rt._voice_session, VoiceSessionTracker)

    def test_idle_timeout_from_config(self) -> None:
        rt = _patched_from_config(voice_session_idle_s=120.0)
        assert rt._voice_session.idle_timeout_s == 120.0

    def test_default_idle_timeout(self) -> None:
        rt = _patched_from_config(voice_session_idle_s=300.0)
        assert rt._voice_session.idle_timeout_s == 300.0

    def test_tracker_starts_with_zero_turns(self) -> None:
        rt = _patched_from_config()
        assert rt._voice_session.turn_count == 0
