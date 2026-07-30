"""Tests for wake_handoff_duration_s wiring through AgentRuntime."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.config import VoiceConfig


class TestWakeHandoffDurationWiring:
    def test_default_wake_handoff_duration_s(self) -> None:
        rt = AgentRuntime(pipeline=MagicMock(), session_mgr=MagicMock())
        assert rt._wake_handoff_duration_s == 10.0

    def test_custom_wake_handoff_duration_s(self) -> None:
        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=30.0,
        )
        assert rt._wake_handoff_duration_s == 30.0

    def test_zero_duration_accepted(self) -> None:
        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=0.0,
        )
        assert rt._wake_handoff_duration_s == 0.0

    def test_voice_config_default_matches_runtime_default(self) -> None:
        cfg = VoiceConfig()
        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=cfg.wake_handoff_duration_s,
        )
        assert rt._wake_handoff_duration_s == 10.0

    def test_voice_config_value_forwarded(self) -> None:
        cfg = VoiceConfig(wake_handoff_duration_s=7.5)
        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=cfg.wake_handoff_duration_s,
        )
        assert rt._wake_handoff_duration_s == 7.5

    @pytest.mark.asyncio
    async def test_revert_uses_wake_handoff_duration_s(self) -> None:
        """_revert_to_wake_mode sleeps for _wake_handoff_duration_s."""
        sleeps: list[float] = []

        async def _fake_sleep(n: float) -> None:
            sleeps.append(n)

        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=0.42,
        )

        with patch("neuralcleave.agent.runtime.asyncio.sleep", _fake_sleep):
            await rt._revert_to_wake_mode()

        assert sleeps == [0.42]
