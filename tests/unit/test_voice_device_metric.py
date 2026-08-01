"""Tests for voice_device_switches_total counter metric."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY, Counter


class TestVoiceDeviceMetric:
    def test_metric_registered(self) -> None:
        assert REGISTRY.get("voice_device_switches_total") is not None

    def test_metric_is_counter(self) -> None:
        assert isinstance(REGISTRY.get("voice_device_switches_total"), Counter)

    def test_increments(self) -> None:
        m = REGISTRY.get("voice_device_switches_total")
        assert isinstance(m, Counter)
        before = m.get()
        REGISTRY.inc("voice_device_switches_total")
        assert m.get() == before + 1.0

    def test_resets_to_zero(self) -> None:
        m = REGISTRY.get("voice_device_switches_total")
        assert isinstance(m, Counter)
        m.reset()
        assert m.get() == 0.0
