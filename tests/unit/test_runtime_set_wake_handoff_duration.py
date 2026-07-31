"""Tests for AgentRuntime.set_wake_handoff_duration()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock())
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeSetWakeHandoffDuration:
    def test_updates_internal_field(self) -> None:
        rt = _make_runtime(wake_handoff_duration_s=10.0)
        rt.set_wake_handoff_duration(20.0)
        assert rt._wake_handoff_duration_s == 20.0

    def test_coerces_to_float(self) -> None:
        rt = _make_runtime()
        rt.set_wake_handoff_duration(5)
        assert isinstance(rt._wake_handoff_duration_s, float)

    def test_default_value_before_set(self) -> None:
        rt = _make_runtime(wake_handoff_duration_s=7.5)
        assert rt._wake_handoff_duration_s == 7.5

    def test_zero_duration_stored(self) -> None:
        rt = _make_runtime()
        rt.set_wake_handoff_duration(0.0)
        assert rt._wake_handoff_duration_s == 0.0

    def test_large_duration_stored(self) -> None:
        rt = _make_runtime()
        rt.set_wake_handoff_duration(300.0)
        assert rt._wake_handoff_duration_s == 300.0

    def test_returns_none(self) -> None:
        rt = _make_runtime()
        result = rt.set_wake_handoff_duration(15.0)
        assert result is None
