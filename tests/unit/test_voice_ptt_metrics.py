"""Tests for PTT metrics: ptt_sessions_total and ptt_recording_active."""

from __future__ import annotations

from neuralcleave.observability.metrics import REGISTRY, Counter, Gauge


class TestPttMetricsRegistered:
    def test_ptt_sessions_total_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401
        assert REGISTRY.get("ptt_sessions_total") is not None

    def test_ptt_recording_active_registered(self) -> None:
        import neuralcleave.observability.metrics  # noqa: F401
        assert REGISTRY.get("ptt_recording_active") is not None

    def test_ptt_sessions_total_is_counter(self) -> None:
        metric = REGISTRY.get("ptt_sessions_total")
        assert isinstance(metric, Counter)

    def test_ptt_recording_active_is_gauge(self) -> None:
        metric = REGISTRY.get("ptt_recording_active")
        assert isinstance(metric, Gauge)

    def test_ptt_sessions_total_description(self) -> None:
        metric = REGISTRY.get("ptt_sessions_total")
        assert "push-to-talk" in metric.description.lower()

    def test_ptt_recording_active_description(self) -> None:
        metric = REGISTRY.get("ptt_recording_active")
        assert "recording" in metric.description.lower()
