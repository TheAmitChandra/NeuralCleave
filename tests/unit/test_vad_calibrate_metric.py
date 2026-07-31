"""Tests for vad_calibrations_total metric registration."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY, Counter


class TestVadCalibrationsMetric:
    def test_vad_calibrations_total_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401

        assert REGISTRY.get("vad_calibrations_total") is not None

    def test_vad_calibrations_total_is_counter(self) -> None:
        metric = REGISTRY.get("vad_calibrations_total")
        assert isinstance(metric, Counter)

    def test_vad_calibrations_total_description_mentions_vad(self) -> None:
        metric = REGISTRY.get("vad_calibrations_total")
        assert "vad" in metric.description.lower() or "calibrat" in metric.description.lower()

    def test_vad_calibrations_total_initial_value_is_zero(self) -> None:
        metric = REGISTRY.get("vad_calibrations_total")
        assert metric.get() == 0.0

    def test_vad_calibrations_total_increments(self) -> None:
        metric = REGISTRY.get("vad_calibrations_total")
        before = metric.get()
        REGISTRY.inc("vad_calibrations_total")
        assert metric.get() == before + 1.0

    def test_vad_calibrations_total_has_description(self) -> None:
        metric = REGISTRY.get("vad_calibrations_total")
        assert len(metric.description) > 0
