"""Tests for wake-word metrics: wake_word_triggers_total and voice_handoff_active."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from neuralcleave.agent.runtime import AgentRuntime
from neuralcleave.observability.metrics import REGISTRY, Counter, Gauge


def _make_runtime() -> AgentRuntime:
    return AgentRuntime(
        pipeline=MagicMock(),
        session_mgr=MagicMock(),
        wake_handoff_duration_s=0.01,
    )


class TestWakeMetricsRegistered:
    def test_wake_word_triggers_total_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401 — triggers registration
        assert REGISTRY.get("wake_word_triggers_total") is not None

    def test_voice_handoff_active_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401
        assert REGISTRY.get("voice_handoff_active") is not None

    def test_wake_word_triggers_is_counter(self) -> None:
        metric = REGISTRY.get("wake_word_triggers_total")
        assert isinstance(metric, Counter)

    def test_voice_handoff_active_is_gauge(self) -> None:
        metric = REGISTRY.get("voice_handoff_active")
        assert isinstance(metric, Gauge)


class TestWakeMetricsOnWakeWord:
    @pytest.mark.asyncio
    async def test_on_wake_word_increments_trigger_counter(self) -> None:
        rt = _make_runtime()
        before = REGISTRY.get("wake_word_triggers_total").get()

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        after = REGISTRY.get("wake_word_triggers_total").get()
        assert after == before + 1.0

    @pytest.mark.asyncio
    async def test_on_wake_word_sets_handoff_active_gauge(self) -> None:
        rt = _make_runtime()

        with patch("neuralcleave.agent.runtime.asyncio.create_task"):
            await rt._on_wake_word()

        assert REGISTRY.get("voice_handoff_active").get() == 1.0

    @pytest.mark.asyncio
    async def test_revert_clears_handoff_active_gauge(self) -> None:
        rt = _make_runtime()
        rt._in_handoff = True

        await rt._revert_to_wake_mode()

        assert REGISTRY.get("voice_handoff_active").get() == 0.0
