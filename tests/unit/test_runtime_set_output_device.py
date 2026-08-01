"""Tests for AgentRuntime.set_output_device()."""

from __future__ import annotations

from unittest.mock import MagicMock

from neuralcleave.agent.runtime import AgentRuntime


def _make_runtime(**kwargs) -> AgentRuntime:
    defaults = dict(pipeline=MagicMock(), session_mgr=MagicMock())
    defaults.update(kwargs)
    return AgentRuntime(**defaults)


class TestSetOutputDevice:
    def test_stores_device(self) -> None:
        rt = _make_runtime()
        rt.set_output_device("USB Speaker")
        assert rt._output_device == "USB Speaker"

    def test_none_clears_device(self) -> None:
        rt = _make_runtime()
        rt.set_output_device("speaker_a")
        rt.set_output_device(None)
        assert rt._output_device is None

    def test_empty_string_clears_device(self) -> None:
        rt = _make_runtime()
        rt.set_output_device("speaker_a")
        rt.set_output_device("")
        assert rt._output_device is None

    def test_increments_metric(self) -> None:
        from neuralcleave.observability.metrics import REGISTRY

        m = REGISTRY.get("voice_device_switches_total")
        assert m is not None
        before = m.get()
        rt = _make_runtime()
        rt.set_output_device("speaker")
        assert m.get() == before + 1.0

    def test_default_output_device_is_none(self) -> None:
        rt = _make_runtime()
        assert rt._output_device is None
