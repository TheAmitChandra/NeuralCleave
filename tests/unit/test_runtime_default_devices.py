"""Tests that AgentRuntime initialises _input_device and _output_device to None."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock())
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestRuntimeDefaultDevices:
    def test_input_device_defaults_to_none(self) -> None:
        rt = _make_runtime()
        assert rt._input_device is None

    def test_output_device_defaults_to_none(self) -> None:
        rt = _make_runtime()
        assert rt._output_device is None

    def test_both_independent(self) -> None:
        rt = _make_runtime()
        rt.set_input_device("mic")
        assert rt._output_device is None

    def test_set_input_does_not_affect_output(self) -> None:
        rt = _make_runtime()
        rt.set_output_device("spk")
        rt.set_input_device("mic")
        assert rt._output_device == "spk"
