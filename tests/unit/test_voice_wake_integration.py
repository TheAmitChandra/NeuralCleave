"""Unit tests for WakeWordDetector wiring in AgentRuntime."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.agent.session import SessionManager

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_runtime(wake_detector=None) -> AgentRuntime:
    pipeline = MagicMock()
    session_mgr = SessionManager()
    rt = AgentRuntime(
        pipeline=pipeline,
        session_mgr=session_mgr,
        wake_detector=wake_detector,
    )
    return rt


# ---------------------------------------------------------------------------
# WakeWordDetector lifecycle in AgentRuntime
# ---------------------------------------------------------------------------

class TestWakeDetectorLifecycle:
    @pytest.mark.asyncio
    async def test_start_calls_detector_start(self) -> None:
        detector = MagicMock()
        detector.start = AsyncMock()
        rt = _make_runtime(wake_detector=detector)
        with (
            patch.object(rt, "_long_term", None),
            patch.object(rt, "_adapters", {}),
            patch("asyncio.create_task"),
        ):
            await rt.start()
        detector.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stop_calls_detector_stop(self) -> None:
        detector = MagicMock()
        detector.stop = AsyncMock()
        rt = _make_runtime(wake_detector=detector)
        rt._gc_task = None
        rt._memory_gc_task = None
        with patch.object(rt, "_adapters", {}):
            await rt.stop()
        detector.stop.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_start_without_detector_does_not_raise(self) -> None:
        rt = _make_runtime(wake_detector=None)
        with (
            patch.object(rt, "_long_term", None),
            patch.object(rt, "_adapters", {}),
            patch("asyncio.create_task"),
        ):
            await rt.start()  # must not raise

    @pytest.mark.asyncio
    async def test_stop_without_detector_does_not_raise(self) -> None:
        rt = _make_runtime(wake_detector=None)
        rt._gc_task = None
        rt._memory_gc_task = None
        with patch.object(rt, "_adapters", {}):
            await rt.stop()  # must not raise

    @pytest.mark.asyncio
    async def test_detector_start_failure_does_not_abort_runtime_start(self) -> None:
        """A failing detector.start() should log a warning but not raise."""
        detector = MagicMock()
        detector.start = AsyncMock(side_effect=RuntimeError("mic unavailable"))
        rt = _make_runtime(wake_detector=detector)
        with (
            patch.object(rt, "_long_term", None),
            patch.object(rt, "_adapters", {}),
            patch("asyncio.create_task"),
        ):
            await rt.start()  # must not raise despite detector failure

    def test_wake_detector_stored_on_init(self) -> None:
        detector = MagicMock()
        rt = _make_runtime(wake_detector=detector)
        assert rt._wake_detector is detector

    def test_no_wake_detector_stored_as_none(self) -> None:
        rt = _make_runtime(wake_detector=None)
        assert rt._wake_detector is None
