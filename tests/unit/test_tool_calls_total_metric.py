"""Tests for tool_calls_total counter registration and behaviour."""

from __future__ import annotations

from neuralcleave.observability.metrics import Counter, REGISTRY


class TestToolCallsTotalMetric:
    def test_metric_is_registered(self) -> None:
        assert REGISTRY.get("tool_calls_total") is not None

    def test_metric_is_counter(self) -> None:
        assert isinstance(REGISTRY.get("tool_calls_total"), Counter)

    def test_metric_resets_to_zero(self) -> None:
        metric = REGISTRY.get("tool_calls_total")
        metric.reset()
        assert metric.get() == 0.0

    def test_metric_increments(self) -> None:
        metric = REGISTRY.get("tool_calls_total")
        metric.reset()
        REGISTRY.inc("tool_calls_total")
        assert metric.get() == 1.0

    def test_metric_increments_by_amount(self) -> None:
        metric = REGISTRY.get("tool_calls_total")
        metric.reset()
        REGISTRY.inc("tool_calls_total", 3.0)
        assert metric.get() == 3.0
