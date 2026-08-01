"""Tests for AgentRuntime.set_input_device()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock())
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestSetInputDevice:
    def test_stores_device(self) -> None:
        rt = _make_runtime()
        rt.set_input_device("USB Mic")
        assert rt._input_device == "USB Mic"

    def test_none_clears_device(self) -> None:
        rt = _make_runtime()
        rt.set_input_device("some_mic")
        rt.set_input_device(None)
        assert rt._input_device is None

    def test_empty_string_clears_device(self) -> None:
        rt = _make_runtime()
        rt.set_input_device("some_mic")
        rt.set_input_device("")
        assert rt._input_device is None

    def test_propagates_to_continuous_listener(self) -> None:
        cont = MagicMock()
        rt = _make_runtime(continuous=cont)
        rt.set_input_device("Headset Mic")
        cont.set_device.assert_called_once_with("Headset Mic")

    def test_propagates_to_ptt(self) -> None:
        ptt = MagicMock()
        ptt._device = None
        rt = _make_runtime(ptt=ptt)
        rt.set_input_device("Headset Mic")
        assert ptt._device == "Headset Mic"

    def test_increments_metric(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        m = REGISTRY.get("voice_device_switches_total")
        assert m is not None
        before = m.get()
        rt = _make_runtime()
        rt.set_input_device("mic")
        assert m.get() == before + 1.0
