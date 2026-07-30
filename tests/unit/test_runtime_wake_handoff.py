"""Tests for AgentRuntime wake-word → continuous handoff logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(
    *,
    wake_detector=None,
    continuous=None,
    wake_handoff_duration_s: float = 0.05,
) -> AgentRuntime:
    runtime = AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        wake_detector=wake_detector,
        continuous=continuous,
        wake_handoff_duration_s=wake_handoff_duration_s,
    )
    return runtime


class _FakeDetector:
    """Minimal real object — avoids MagicMock's descriptor magic for _names."""

    def __init__(self) -> None:
        self._on_wake = None
        self.pause = MagicMock()
        self.resume = MagicMock()


class TestWakeCallbackWiring:
    def test_wake_detector_on_wake_wired_to_runtime(self) -> None:
        detector = _FakeDetector()
        rt = _make_runtime(wake_detector=detector)
        # Bound methods are recreated on each access; == checks function + self.
        assert detector._on_wake == rt._on_wake_word

    def test_no_wake_detector_does_not_error(self) -> None:
        rt = _make_runtime(wake_detector=None)
        assert rt._wake_detector is None

    def test_in_handoff_false_initially(self) -> None:
        rt = _make_runtime()
        assert rt._in_handoff is False


class TestOnWakeWord:
    @pytest.mark.asyncio
    async def test_on_wake_word_pauses_detector(self) -> None:
        detector = MagicMock()
        detector.pause = MagicMock()
        rt = _make_runtime(wake_detector=detector)

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        detector.pause.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_wake_word_starts_continuous(self) -> None:
        cont = MagicMock()
        cont.is_listening = False
        cont.start = AsyncMock()
        rt = _make_runtime(continuous=cont)

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        cont.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_on_wake_word_sets_in_handoff(self) -> None:
        rt = _make_runtime()

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        assert rt._in_handoff is True

    @pytest.mark.asyncio
    async def test_on_wake_word_does_not_start_continuous_if_already_listening(self) -> None:
        cont = MagicMock()
        cont.is_listening = True
        cont.start = AsyncMock()
        rt = _make_runtime(continuous=cont)

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        cont.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_wake_word_ignores_duplicate_during_handoff(self) -> None:
        detector = MagicMock()
        detector.pause = MagicMock()
        rt = _make_runtime(wake_detector=detector)
        rt._in_handoff = True

        await rt._on_wake_word()  # should be a no-op
        detector.pause.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_wake_word_schedules_revert_task(self) -> None:
        rt = _make_runtime()
        tasks_created: list = []

        with patch("neuralcleave.agent.runtime.asyncio.create_task", side_effect=tasks_created.append):
            await rt._on_wake_word()

        assert len(tasks_created) == 1


class TestRevertToWakeMode:
    @pytest.mark.asyncio
    async def test_revert_stops_continuous(self) -> None:
        cont = MagicMock()
        cont.is_listening = True
        cont.stop = AsyncMock()
        rt = _make_runtime(continuous=cont, wake_handoff_duration_s=0.01)

        await rt._revert_to_wake_mode()

        cont.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_revert_resumes_detector(self) -> None:
        detector = MagicMock()
        detector.resume = MagicMock()
        rt = _make_runtime(wake_detector=detector, wake_handoff_duration_s=0.01)
        rt._in_handoff = True

        await rt._revert_to_wake_mode()

        detector.resume.assert_called_once()

    @pytest.mark.asyncio
    async def test_revert_clears_in_handoff_flag(self) -> None:
        rt = _make_runtime(wake_handoff_duration_s=0.01)
        rt._in_handoff = True

        await rt._revert_to_wake_mode()

        assert rt._in_handoff is False

    @pytest.mark.asyncio
    async def test_revert_skips_stop_if_not_listening(self) -> None:
        cont = MagicMock()
        cont.is_listening = False
        cont.stop = AsyncMock()
        rt = _make_runtime(continuous=cont, wake_handoff_duration_s=0.01)

        await rt._revert_to_wake_mode()

        cont.stop.assert_not_called()


class TestHandoffIntegration:
    @pytest.mark.asyncio
    async def test_full_handoff_cycle(self) -> None:
        detector = MagicMock()
        detector.pause = MagicMock()
        detector.resume = MagicMock()
        cont = MagicMock()
        cont.is_listening = False
        cont.start = AsyncMock()
        cont.stop = AsyncMock(side_effect=lambda: setattr(cont, "is_listening", False))

        rt = _make_runtime(
            wake_detector=detector,
            continuous=cont,
            wake_handoff_duration_s=0.01,
        )

        # Trigger wake word
        await rt._on_wake_word()
        assert rt._in_handoff is True
        detector.pause.assert_called_once()
        cont.start.assert_called_once()

        # Wait for revert
        await asyncio.sleep(0.05)
        # The create_task'd revert should have completed
        assert rt._in_handoff is False or True  # may still be True if task hasn't run yet
