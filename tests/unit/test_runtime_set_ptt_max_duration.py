"""Tests for AgentRuntime.set_ptt_max_duration()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), ptt=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeSetPttMaxDuration:
    def test_returns_false_when_no_ptt(self) -> None:
        rt = _make_runtime(ptt=None)
        assert rt.set_ptt_max_duration(60.0) is False

    def test_returns_true_when_ptt_configured(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        assert rt.set_ptt_max_duration(60.0) is True

    def test_updates_ptt_max_duration_s(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        rt.set_ptt_max_duration(45.0)
        assert ptt._max_duration_s == 45.0

    def test_coerces_to_float(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        rt.set_ptt_max_duration(30)
        assert isinstance(ptt._max_duration_s, float)

    def test_zero_duration_stored(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        rt.set_ptt_max_duration(0.0)
        assert ptt._max_duration_s == 0.0

    def test_large_duration_stored(self) -> None:
        ptt = MagicMock()
        rt = _make_runtime(ptt=ptt)
        rt.set_ptt_max_duration(600.0)
        assert ptt._max_duration_s == 600.0
