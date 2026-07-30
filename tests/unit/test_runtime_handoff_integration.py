"""Integration tests for the full wake-word → continuous → revert handoff cycle."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime


class _FakeDetector:
    def __init__(self) -> None:
        self._on_wake = None
        self.pause = MagicMock()
        self.resume = MagicMock()


class _FakeContinuous:
    def __init__(self) -> None:
        self.is_listening = False
        self.start = AsyncMock(side_effect=self._set_listening)
        self.stop = AsyncMock(side_effect=self._clear_listening)

    def _set_listening(self) -> None:
        self.is_listening = True

    def _clear_listening(self) -> None:
        self.is_listening = False


def _make_runtime(duration: float = 0.02) -> tuple[AgentRuntime, _FakeDetector, _FakeContinuous]:
    detector = _FakeDetector()
    cont = _FakeContinuous()
    rt = AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        wake_detector=detector,
        continuous=cont,
        wake_handoff_duration_s=duration,
    )
    return rt, detector, cont


class TestHandoffIntegration:
    @pytest.mark.asyncio
    async def test_wake_fires_start_continuous(self) -> None:
        rt, detector, cont = _make_runtime()

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        cont.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_wake_fires_pause_detector(self) -> None:
        rt, detector, cont = _make_runtime()

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        detector.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_full_cycle_end_to_end(self) -> None:
        rt, detector, cont = _make_runtime(duration=0.02)

        # 1. trigger wake
        await rt._on_wake_word()
        assert rt._in_handoff is True
        detector.pause.assert_called_once()
        cont.start.assert_called_once()

        # 2. wait for revert (with some margin)
        await asyncio.sleep(0.1)
        # asyncio.create_task inside _on_wake_word must have scheduled revert
        # Since we didn't patch create_task, it ran; wait for it
        # Give the event loop a turn
        for _ in range(20):
            await asyncio.sleep(0.01)
            if not rt._in_handoff:
                break

        assert rt._in_handoff is False
        detector.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_wake_during_handoff_ignored(self) -> None:
        rt, detector, _ = _make_runtime()
        rt._in_handoff = True

        await rt._on_wake_word()

        detector.pause.assert_not_called()

    @pytest.mark.asyncio
    async def test_revert_resumes_detector_and_clears_flag(self) -> None:
        rt, detector, cont = _make_runtime(duration=0.01)
        rt._in_handoff = True
        cont.is_listening = True

        await rt._revert_to_wake_mode()

        assert rt._in_handoff is False
        detector.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_continuous_stopped_on_revert(self) -> None:
        rt, _, cont = _make_runtime(duration=0.01)
        cont.is_listening = True

        await rt._revert_to_wake_mode()

        cont.stop.assert_called_once()
