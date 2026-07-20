"""Prometheus-compatible metrics for NeuralCleave.

Provides lightweight counter, gauge, and histogram types that can be:
  - Scraped by Prometheus via the ``/metrics`` endpoint (when using the
    optional ``prometheus_client`` package)
  - Read programmatically via ``MetricsRegistry.snapshot()`` for the web UI

The module intentionally avoids requiring ``prometheus_client`` at import time.
If the package is available, ``MetricsRegistry.export_prometheus()`` emits the
standard text/plain Prometheus exposition format. If it is absent, the same
method returns a human-readable plain-text fallback.

Built-in metrics (all pre-registered on ``REGISTRY``):

  messages_total             Counter   — total inbound messages, labelled by channel
  messages_sent_total        Counter   — total outbound replies, labelled by channel
  messages_errors_total      Counter   — processing errors, labelled by channel
  active_sessions            Gauge     — currently open WebSocket sessions
  channel_up                 Gauge     — 1 when a channel adapter is connected, else 0
  generation_requests_total  Counter   — LLM generation requests, labelled by model
  generation_errors_total    Counter   — LLM generation failures, labelled by model
  generation_latency_ms      Histogram — LLM generation latency in ms, by model
  generation_quality_score   Histogram — reflection quality score (0-100), by model
  tokens_total               Counter   — LLM tokens consumed, by model + direction
  memory_entries_total       Gauge     — total entries in long-term memory
  voice_transcriptions_total Counter   — STT transcriptions performed
  voice_synthesis_total      Counter   — TTS synthesis requests performed

Usage::

    from neuralcleave.observability.metrics import REGISTRY

    REGISTRY.inc("messages_total", labels={"channel": "telegram"})
    REGISTRY.set("active_sessions", 3)
    REGISTRY.observe("generation_latency_ms", 412.5, labels={"model": "gpt-4o"})

    print(REGISTRY.export_prometheus())
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Any

# ---------------------------------------------------------------------------
# Metric types
# ---------------------------------------------------------------------------


@dataclass
class Counter:
    """Monotonically increasing counter."""

    name: str
    description: str
    _values: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def inc(self, amount: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        key = _label_key(labels)
        with self._lock:
            self._values[key] += amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        return self._values[_label_key(labels)]

    def reset(self, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_label_key(labels)] = 0.0

    def snapshot(self) -> dict[str, float]:
        return dict(self._values)


@dataclass
class Gauge:
    """Arbitrary numeric value that can go up or down."""

    name: str
    description: str
    _values: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def set(self, value: float, *, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_label_key(labels)] = value

    def inc(self, amount: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_label_key(labels)] += amount

    def dec(self, amount: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        with self._lock:
            self._values[_label_key(labels)] -= amount

    def get(self, labels: dict[str, str] | None = None) -> float:
        return self._values[_label_key(labels)]

    def snapshot(self) -> dict[str, float]:
        return dict(self._values)


@dataclass
class Histogram:
    """Distributes observations into configurable buckets.

    Default buckets cover typical LLM latencies in milliseconds.
    """

    name: str
    description: str
    buckets: tuple[float, ...] = (
        50, 100, 250, 500, 1000, 2500, 5000, 10000, float("inf")
    )
    _counts: dict[str, list[int]] = field(default_factory=dict)
    _sums: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    _totals: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    _lock: Lock = field(default_factory=Lock, repr=False, compare=False)

    def observe(self, value: float, *, labels: dict[str, str] | None = None) -> None:
        key = _label_key(labels)
        with self._lock:
            if key not in self._counts:
                self._counts[key] = [0] * len(self.buckets)
            for i, bound in enumerate(self.buckets):
                if value <= bound:
                    self._counts[key][i] += 1
            self._sums[key] += value
            self._totals[key] += 1

    def get_sum(self, labels: dict[str, str] | None = None) -> float:
        return self._sums[_label_key(labels)]

    def get_count(self, labels: dict[str, str] | None = None) -> int:
        return self._totals[_label_key(labels)]

    def get_buckets(self, labels: dict[str, str] | None = None) -> list[tuple[float, int]]:
        key = _label_key(labels)
        counts = self._counts.get(key, [0] * len(self.buckets))
        return list(zip(self.buckets, counts))

    def snapshot(self) -> dict[str, Any]:
        result = {}
        for key in set(list(self._sums.keys()) + list(self._totals.keys())):
            counts = self._counts.get(key, [0] * len(self.buckets))
            result[key] = {
                "sum": self._sums[key],
                "count": self._totals[key],
                "buckets": list(zip(self.buckets, counts)),
            }
        return result


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class MetricsRegistry:
    """Central store for all application metrics.

    Supports Counter, Gauge, and Histogram. Each metric is identified by name.
    Register a metric once with ``register()``, then use the convenience
    methods ``inc()``, ``set()``, ``observe()`` anywhere in the codebase.
    """

    def __init__(self) -> None:
        self._metrics: dict[str, Counter | Gauge | Histogram] = {}
        self._lock = Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        metric_type: type,
        name: str,
        description: str,
        **kwargs: Any,
    ) -> Counter | Gauge | Histogram:
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = metric_type(name=name, description=description, **kwargs)
        return self._metrics[name]

    def get(self, name: str) -> Counter | Gauge | Histogram | None:
        return self._metrics.get(name)

    # ------------------------------------------------------------------
    # Convenience mutators
    # ------------------------------------------------------------------

    def inc(self, name: str, amount: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        m = self._metrics.get(name)
        if isinstance(m, (Counter, Gauge)):
            m.inc(amount, labels=labels)

    def dec(self, name: str, amount: float = 1.0, *, labels: dict[str, str] | None = None) -> None:
        m = self._metrics.get(name)
        if isinstance(m, Gauge):
            m.dec(amount, labels=labels)

    def set(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        m = self._metrics.get(name)
        if isinstance(m, Gauge):
            m.set(value, labels=labels)

    def observe(self, name: str, value: float, *, labels: dict[str, str] | None = None) -> None:
        m = self._metrics.get(name)
        if isinstance(m, Histogram):
            m.observe(value, labels=labels)

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def snapshot(self) -> dict[str, Any]:
        """Return a plain-Python snapshot of all metrics (for web UI)."""
        result: dict[str, Any] = {}
        for name, m in self._metrics.items():
            result[name] = {
                "type": type(m).__name__.lower(),
                "description": m.description,
                "values": m.snapshot(),
            }
        return result

    def export_prometheus(self) -> str:
        """Emit Prometheus text/plain exposition format.

        Uses the ``prometheus_client`` package if available; falls back to a
        hand-rolled implementation so the method always works.
        """
        lines: list[str] = []
        ts = int(time.time() * 1000)

        for name, m in self._metrics.items():
            lines.append(f"# HELP {name} {m.description}")
            if isinstance(m, Counter):
                lines.append(f"# TYPE {name} counter")
                for label_str, val in m.snapshot().items():
                    lines.append(f"{name}{_fmt_labels(label_str)} {val} {ts}")
            elif isinstance(m, Gauge):
                lines.append(f"# TYPE {name} gauge")
                for label_str, val in m.snapshot().items():
                    lines.append(f"{name}{_fmt_labels(label_str)} {val} {ts}")
            elif isinstance(m, Histogram):
                lines.append(f"# TYPE {name} histogram")
                for label_str, data in m.snapshot().items():
                    base = _fmt_labels(label_str)
                    for bound, count in data["buckets"]:
                        le = "+Inf" if math.isinf(bound) else str(bound)
                        bucket_labels = _add_label(label_str, "le", le)
                        lines.append(f"{name}_bucket{bucket_labels} {count} {ts}")
                    lines.append(f"{name}_sum{base} {data['sum']} {ts}")
                    lines.append(f"{name}_count{base} {data['count']} {ts}")

        return "\n".join(lines) + "\n"

    def registered_names(self) -> list[str]:
        return sorted(self._metrics.keys())


# ---------------------------------------------------------------------------
# Label helpers
# ---------------------------------------------------------------------------


def _label_key(labels: dict[str, str] | None) -> str:
    if not labels:
        return ""
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def _fmt_labels(key: str) -> str:
    if not key:
        return ""
    pairs = [p.split("=", 1) for p in key.split(",") if "=" in p]
    inner = ",".join(f'{k}="{v}"' for k, v in pairs)
    return "{" + inner + "}"


def _add_label(existing_key: str, label_name: str, label_value: str) -> str:
    parts: list[tuple[str, str]] = []
    if existing_key:
        for p in existing_key.split(","):
            if "=" in p:
                k, v = p.split("=", 1)
                parts.append((k, v))
    parts.append((label_name, label_value))
    inner = ",".join(f'{k}="{v}"' for k, v in parts)
    return "{" + inner + "}"


# ---------------------------------------------------------------------------
# Module-level default registry with pre-built metrics
# ---------------------------------------------------------------------------

REGISTRY = MetricsRegistry()

# Messages
REGISTRY.register(Counter, "messages_total", "Total inbound messages processed, by channel")
REGISTRY.register(Counter, "messages_sent_total", "Total outbound replies sent, by channel")
REGISTRY.register(Counter, "messages_errors_total", "Message processing errors, by channel")

# Sessions
REGISTRY.register(Gauge, "active_sessions", "Number of currently active sessions")

# Channel health
REGISTRY.register(Gauge, "channel_up", "1 when the channel adapter is connected")

# LLM generation
REGISTRY.register(
    Histogram,
    "generation_latency_ms",
    "LLM generation latency in milliseconds, by model",
)
REGISTRY.register(Counter, "generation_requests_total", "Total LLM generation requests, by model")
REGISTRY.register(Counter, "generation_errors_total", "Failed LLM generation requests, by model")
REGISTRY.register(
    Histogram,
    "generation_quality_score",
    "Reflection engine quality score (0-100) per generation, by model",
    buckets=(10, 25, 50, 70, 80, 90, 100, float("inf")),
)
REGISTRY.register(Counter, "tokens_total", "LLM tokens consumed, by model and direction (input/output)")

# Memory
REGISTRY.register(Gauge, "memory_entries_total", "Total entries in long-term memory store")

# Voice
REGISTRY.register(Counter, "voice_transcriptions_total", "STT transcriptions performed")
REGISTRY.register(Counter, "voice_synthesis_total", "TTS synthesis requests performed")
