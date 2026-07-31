"""Tests for AgentRuntime.set_vad_threshold()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock(), continuous=None)
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeSetVadThreshold:
    def test_returns_false_when_no_continuous(self) -> None:
        rt = _make_runtime(continuous=None)
        assert rt.set_vad_threshold(400.0) is False

    def test_returns_true_when_continuous_present(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        assert rt.set_vad_threshold(400.0) is True

    def test_calls_set_silence_threshold(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        rt.set_vad_threshold(350.0)
        cont.set_silence_threshold.assert_called_once_with(350.0)

    def test_passes_float_value(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        rt.set_vad_threshold(200)
        cont.set_silence_threshold.assert_called_once_with(200)

    def test_zero_threshold_allowed(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        result = rt.set_vad_threshold(0.0)
        assert result is True

    def test_high_threshold_allowed(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        result = rt.set_vad_threshold(9999.0)
        assert result is True
