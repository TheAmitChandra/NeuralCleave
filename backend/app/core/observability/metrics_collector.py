"""Prometheus Metrics Collector — CortexFlow runtime telemetry aggregator.

Provides a lightweight in-memory layer that accumulates event counts and
timings independently of the Prometheus client library.  Useful for:
    - local dashboards when ``prometheus-client`` is not installed
    - unit tests that must not touch the global Prometheus registry
    - internal rate calculations (events/sec over a sliding window)

Usage::

    collector = MetricsCollector()
    collector.increment("tool.calls", labels={"tool": "shell.execute"})
    collector.record_duration("tool.latency", 0.42, labels={"tool": "shell.execute"})

    snapshot = collector.snapshot()
    print(snapshot.counters)  # {"tool.calls{tool=shell.execute}": 1}
    print(snapshot.total_events)  # 1
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _label_key(name: str, labels: dict[str, str] | None) -> str:
    """Build a canonical string key from a metric name + optional labels."""
    if not labels:
        return name
    pairs = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
    return f"{name}{{{pairs}}}"


# ---------------------------------------------------------------------------
# Snapshot dataclass
# ---------------------------------------------------------------------------


@dataclass
class MetricsSnapshot:
    """Point-in-time snapshot of all collected metrics.

    Attributes:
        timestamp:   Unix epoch when the snapshot was taken.
        counters:    Cumulative event counts keyed by label-annotated name.
        durations:   All recorded duration samples keyed by metric name.
        gauges:      Current gauge values.
    """

    timestamp: float
    counters: dict[str, int]
    durations: dict[str, list[float]]
    gauges: dict[str, float]

    @property
    def total_events(self) -> int:
        return sum(self.counters.values())

    def average_duration(self, metric_name: str) -> float | None:
        """Return the mean of all recorded durations for *metric_name*, or None."""
        samples = self.durations.get(metric_name, [])
        if not samples:
            return None
        return sum(samples) / len(samples)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "counters": dict(self.counters),
            "gauges": dict(self.gauges),
            "total_events": self.total_events,
        }


# ---------------------------------------------------------------------------
# MetricsCollector
# ---------------------------------------------------------------------------


class MetricsCollector:
    """Lightweight in-memory metrics aggregator.

    All operations are synchronous and thread-safe for single-threaded use.

    Parameters:
        rate_window_seconds: Window size for rate calculations.
    """

    def __init__(self, rate_window_seconds: float = 60.0) -> None:
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = defaultdict(float)
        self._durations: dict[str, list[float]] = defaultdict(list)
        self._event_times: deque[float] = deque()
        self._rate_window = rate_window_seconds

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def increment(
        self,
        name: str,
        amount: int = 1,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Increment a named counter by *amount*."""
        key = _label_key(name, labels)
        self._counters[key] += amount
        now = time.monotonic()
        self._event_times.append(now)
        # Prune old events outside the window
        cutoff = now - self._rate_window
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()

    def record_duration(
        self,
        name: str,
        seconds: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Record a duration sample (in seconds)."""
        key = _label_key(name, labels)
        self._durations[key].append(seconds)

    def set_gauge(
        self,
        name: str,
        value: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Set a gauge to an absolute value."""
        key = _label_key(name, labels)
        self._gauges[key] = value

    def adjust_gauge(
        self,
        name: str,
        delta: float,
        *,
        labels: dict[str, str] | None = None,
    ) -> None:
        """Adjust a gauge by *delta* (positive = up, negative = down)."""
        key = _label_key(name, labels)
        self._gauges[key] += delta

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_count(self, name: str, *, labels: dict[str, str] | None = None) -> int:
        """Return the current count for a named counter (0 if not seen)."""
        return self._counters.get(_label_key(name, labels), 0)

    def get_gauge(self, name: str, *, labels: dict[str, str] | None = None) -> float:
        """Return the current gauge value (0.0 if not set)."""
        return self._gauges.get(_label_key(name, labels), 0.0)

    def get_durations(self, name: str, *, labels: dict[str, str] | None = None) -> list[float]:
        """Return all recorded duration samples for a metric."""
        return list(self._durations.get(_label_key(name, labels), []))

    def average_duration(self, name: str, *, labels: dict[str, str] | None = None) -> float | None:
        """Return average duration, or None if no samples recorded."""
        samples = self._durations[_label_key(name, labels)]
        if not samples:
            return None
        return sum(samples) / len(samples)

    def event_rate(self) -> float:
        """Return events per second over the last ``rate_window_seconds``."""
        now = time.monotonic()
        cutoff = now - self._rate_window
        while self._event_times and self._event_times[0] < cutoff:
            self._event_times.popleft()
        if self._rate_window <= 0:
            return 0.0
        return len(self._event_times) / self._rate_window

    def snapshot(self) -> MetricsSnapshot:
        """Return an immutable snapshot of the current metric state."""
        return MetricsSnapshot(
            timestamp=time.time(),
            counters=dict(self._counters),
            durations={k: list(v) for k, v in self._durations.items()},
            gauges=dict(self._gauges),
        )

    @property
    def counter_count(self) -> int:
        """Number of distinct counter series tracked."""
        return len(self._counters)

    @property
    def gauge_count(self) -> int:
        """Number of distinct gauge series tracked."""
        return len(self._gauges)

    def reset(self) -> None:
        """Clear all collected metrics."""
        self._counters.clear()
        self._gauges.clear()
        self._durations.clear()
        self._event_times.clear()
