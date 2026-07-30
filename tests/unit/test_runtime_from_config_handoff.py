"""Tests for wake_handoff_duration_s wiring through AgentRuntime."""

from __future__ import annotations

from unittest.mock import MagicMock

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

    def test_revert_uses_wake_handoff_duration_s(self) -> None:
        """_revert_to_wake_mode sleeps for _wake_handoff_duration_s."""
        import asyncio
        from unittest.mock import patch

        sleeps: list[float] = []

        async def _fake_sleep(n: float) -> None:
            sleeps.append(n)

        rt = AgentRuntime(
            pipeline=MagicMock(),
            session_mgr=MagicMock(),
            wake_handoff_duration_s=0.42,
        )

        async def _run():
            with patch("neuralcleave.agent.runtime.asyncio.sleep", _fake_sleep):
                await rt._revert_to_wake_mode()

        asyncio.get_event_loop().run_until_complete(_run())
        assert sleeps == [0.42]
