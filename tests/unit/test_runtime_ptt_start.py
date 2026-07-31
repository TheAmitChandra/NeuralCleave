"""Tests for AgentRuntime.ptt_start()."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(ptt=None) -> AgentRuntime:
    return AgentRuntime(pipeline=MagicMock(), session_mgr=MagicMock(), ptt=ptt)


class TestPttStart:
    @pytest.mark.asyncio
    async def test_returns_false_when_ptt_is_none(self) -> None:
        rt = _make_runtime(ptt=None)
        result = await rt.ptt_start()
        assert result is False

    @pytest.mark.asyncio
    async def test_returns_false_when_already_recording(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = True
        ptt.start = AsyncMock()
        rt = _make_runtime(ptt=ptt)

        result = await rt.ptt_start()
        assert result is False
        ptt.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_true_when_started(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = False
        ptt.start = AsyncMock()
        rt = _make_runtime(ptt=ptt)

        result = await rt.ptt_start()
        assert result is True

    @pytest.mark.asyncio
    async def test_calls_ptt_start(self) -> None:
        ptt = MagicMock()
        ptt.is_recording = False
        ptt.start = AsyncMock()
        rt = _make_runtime(ptt=ptt)

        await rt.ptt_start()
        ptt.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_sets_ptt_recording_active_gauge(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        ptt = MagicMock()
        ptt.is_recording = False
        ptt.start = AsyncMock()
        rt = _make_runtime(ptt=ptt)

        await rt.ptt_start()
        assert REGISTRY.get("ptt_recording_active").get() == 1.0
