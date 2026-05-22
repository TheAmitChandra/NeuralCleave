"""Tests for MetricsCollector and MetricsSnapshot."""

from __future__ import annotations

import time

import pytest

from app.core.observability.metrics_collector import MetricsCollector, MetricsSnapshot, _label_key


# ===========================================================================
# TestLabelKey
# ===========================================================================

class TestLabelKey:
    def test_no_labels(self) -> None:
        assert _label_key("metric", None) == "metric"

    def test_with_labels(self) -> None:
        key = _label_key("tool.calls", {"tool": "shell", "env": "prod"})
        assert key == "tool.calls{env=prod,tool=shell}"

    def test_labels_sorted_alphabetically(self) -> None:
        key = _label_key("m", {"z": "1", "a": "2"})
        assert key.startswith("m{a=2")


# ===========================================================================
# TestMetricsCollectorIncrement
# ===========================================================================

class TestMetricsCollectorIncrement:
    def test_increment_once(self) -> None:
        c = MetricsCollector()
        c.increment("req")
        assert c.get_count("req") == 1

    def test_increment_multiple_times(self) -> None:
        c = MetricsCollector()
        for _ in range(5):
            c.increment("req")
        assert c.get_count("req") == 5

    def test_increment_by_custom_amount(self) -> None:
        c = MetricsCollector()
        c.increment("tokens", 100)
        assert c.get_count("tokens") == 100

    def test_increment_with_labels(self) -> None:
        c = MetricsCollector()
        c.increment("req", labels={"method": "GET"})
        c.increment("req", labels={"method": "POST"})
        assert c.get_count("req", labels={"method": "GET"}) == 1
        assert c.get_count("req", labels={"method": "POST"}) == 1

    def test_different_label_sets_are_independent(self) -> None:
        c = MetricsCollector()
        c.increment("m", labels={"a": "1"})
        c.increment("m", labels={"a": "2"})
        c.increment("m", labels={"a": "2"})
        assert c.get_count("m", labels={"a": "1"}) == 1
        assert c.get_count("m", labels={"a": "2"}) == 2

    def test_unknown_counter_returns_zero(self) -> None:
        c = MetricsCollector()
        assert c.get_count("nonexistent") == 0

    def test_counter_count_property(self) -> None:
        c = MetricsCollector()
        c.increment("a")
        c.increment("b")
        assert c.counter_count == 2


# ===========================================================================
# TestMetricsCollectorDurations
# ===========================================================================

class TestMetricsCollectorDurations:
    def test_record_single_duration(self) -> None:
        c = MetricsCollector()
        c.record_duration("latency", 0.42)
        assert c.get_durations("latency") == [0.42]

    def test_record_multiple_durations(self) -> None:
        c = MetricsCollector()
        for v in [0.1, 0.2, 0.3]:
            c.record_duration("latency", v)
        assert len(c.get_durations("latency")) == 3

    def test_average_duration(self) -> None:
        c = MetricsCollector()
        c.record_duration("latency", 1.0)
        c.record_duration("latency", 3.0)
        assert c.average_duration("latency") == pytest.approx(2.0)

    def test_average_duration_no_samples_returns_none(self) -> None:
        c = MetricsCollector()
        assert c.average_duration("latency") is None

    def test_durations_with_labels(self) -> None:
        c = MetricsCollector()
        c.record_duration("latency", 0.5, labels={"tier": "qdrant"})
        c.record_duration("latency", 1.0, labels={"tier": "neo4j"})
        assert c.get_durations("latency", labels={"tier": "qdrant"}) == [0.5]
        assert c.get_durations("latency", labels={"tier": "neo4j"}) == [1.0]


# ===========================================================================
# TestMetricsCollectorGauges
# ===========================================================================

class TestMetricsCollectorGauges:
    def test_set_gauge(self) -> None:
        c = MetricsCollector()
        c.set_gauge("active_agents", 5.0)
        assert c.get_gauge("active_agents") == 5.0

    def test_adjust_gauge_up(self) -> None:
        c = MetricsCollector()
        c.set_gauge("active_agents", 3.0)
        c.adjust_gauge("active_agents", 2.0)
        assert c.get_gauge("active_agents") == 5.0

    def test_adjust_gauge_down(self) -> None:
        c = MetricsCollector()
        c.set_gauge("active_agents", 5.0)
        c.adjust_gauge("active_agents", -2.0)
        assert c.get_gauge("active_agents") == 3.0

    def test_unknown_gauge_returns_zero(self) -> None:
        c = MetricsCollector()
        assert c.get_gauge("nonexistent") == 0.0

    def test_gauge_count_property(self) -> None:
        c = MetricsCollector()
        c.set_gauge("x", 1.0)
        c.set_gauge("y", 2.0)
        assert c.gauge_count == 2


# ===========================================================================
# TestMetricsSnapshot
# ===========================================================================

class TestMetricsSnapshot:
    def test_snapshot_contains_counters(self) -> None:
        c = MetricsCollector()
        c.increment("req", 3)
        snap = c.snapshot()
        assert snap.counters["req"] == 3

    def test_snapshot_total_events(self) -> None:
        c = MetricsCollector()
        c.increment("a", 2)
        c.increment("b", 3)
        snap = c.snapshot()
        assert snap.total_events == 5

    def test_snapshot_average_duration(self) -> None:
        c = MetricsCollector()
        c.record_duration("lat", 1.0)
        c.record_duration("lat", 3.0)
        snap = c.snapshot()
        assert snap.average_duration("lat") == pytest.approx(2.0)

    def test_snapshot_average_duration_missing_returns_none(self) -> None:
        snap = MetricsSnapshot(timestamp=0.0, counters={}, durations={}, gauges={})
        assert snap.average_duration("missing") is None

    def test_snapshot_to_dict(self) -> None:
        c = MetricsCollector()
        c.increment("requests", 5)
        c.set_gauge("workers", 3.0)
        d = c.snapshot().to_dict()
        assert d["counters"]["requests"] == 5
        assert d["gauges"]["workers"] == 3.0
        assert "timestamp" in d
        assert d["total_events"] == 5

    def test_snapshot_is_independent_copy(self) -> None:
        c = MetricsCollector()
        c.increment("req")
        snap = c.snapshot()
        c.increment("req")  # mutate after snapshot
        assert snap.counters["req"] == 1  # snapshot unchanged


# ===========================================================================
# TestMetricsCollectorEventRate
# ===========================================================================

class TestMetricsCollectorEventRate:
    def test_event_rate_zero_when_empty(self) -> None:
        c = MetricsCollector(rate_window_seconds=60.0)
        assert c.event_rate() == pytest.approx(0.0)

    def test_event_rate_after_increments(self) -> None:
        c = MetricsCollector(rate_window_seconds=60.0)
        for _ in range(30):
            c.increment("req")
        rate = c.event_rate()
        assert rate == pytest.approx(0.5)  # 30/60


# ===========================================================================
# TestMetricsCollectorReset
# ===========================================================================

class TestMetricsCollectorReset:
    def test_reset_clears_counters(self) -> None:
        c = MetricsCollector()
        c.increment("req", 5)
        c.reset()
        assert c.get_count("req") == 0
        assert c.counter_count == 0

    def test_reset_clears_gauges(self) -> None:
        c = MetricsCollector()
        c.set_gauge("g", 10.0)
        c.reset()
        assert c.get_gauge("g") == 0.0
        assert c.gauge_count == 0

    def test_reset_clears_durations(self) -> None:
        c = MetricsCollector()
        c.record_duration("lat", 1.0)
        c.reset()
        assert c.get_durations("lat") == []
