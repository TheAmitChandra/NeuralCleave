"""AutoScaler — CortexFlow horizontal pod autoscaling logic.

Evaluates runtime metrics (CPU, memory, request rate, queue depth) and
produces scaling decisions (scale_up | scale_down | maintain).

The scaling algorithm uses configurable high/low watermarks for each
dimension and returns the first action triggered by any dimension, in
priority order: CPU > memory > queue_depth > request_rate.

Usage::

    scaler = AutoScaler(min_replicas=2, max_replicas=10)
    metrics = ScalingMetrics(cpu_usage=0.85, memory_usage=0.4,
                             request_rate=120.0, queue_depth=5)
    decision = scaler.evaluate(metrics)
    print(decision.action)     # "scale_up"
    print(decision.replicas)   # 3  (current + 1)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ScalingMetrics:
    """Point-in-time resource utilisation snapshot.

    Attributes:
        cpu_usage:      CPU utilisation as a fraction [0.0, 1.0].
        memory_usage:   Memory utilisation as a fraction [0.0, 1.0].
        request_rate:   Incoming requests per second.
        queue_depth:    Pending task queue depth (absolute count).
    """

    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    request_rate: float = 0.0
    queue_depth: int = 0

    def __post_init__(self) -> None:
        if not (0.0 <= self.cpu_usage <= 1.0):
            raise ValueError("cpu_usage must be between 0.0 and 1.0")
        if not (0.0 <= self.memory_usage <= 1.0):
            raise ValueError("memory_usage must be between 0.0 and 1.0")
        if self.request_rate < 0:
            raise ValueError("request_rate must be >= 0")
        if self.queue_depth < 0:
            raise ValueError("queue_depth must be >= 0")

    def to_dict(self) -> dict[str, Any]:
        return {
            "cpu_usage": self.cpu_usage,
            "memory_usage": self.memory_usage,
            "request_rate": self.request_rate,
            "queue_depth": self.queue_depth,
        }


@dataclass
class ScalingDecision:
    """Result of an autoscaling evaluation.

    Attributes:
        action:     "scale_up" | "scale_down" | "maintain".
        replicas:   Target replica count after the decision.
        reason:     Human-readable rationale.
        confidence: Score 0.0–1.0 indicating how firmly the rule fired.
        trigger:    The metric dimension that drove the decision.
    """

    action: str  # "scale_up" | "scale_down" | "maintain"
    replicas: int
    reason: str
    confidence: float = 1.0
    trigger: str = ""

    def __post_init__(self) -> None:
        if self.action not in ("scale_up", "scale_down", "maintain"):
            raise ValueError(
                f"action must be 'scale_up', 'scale_down', or 'maintain'; got {self.action!r}"
            )
        if self.replicas < 1:
            raise ValueError("replicas must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "replicas": self.replicas,
            "reason": self.reason,
            "confidence": self.confidence,
            "trigger": self.trigger,
        }


# ---------------------------------------------------------------------------
# AutoScaler
# ---------------------------------------------------------------------------

class AutoScaler:
    """Horizontal pod autoscaler based on multi-metric watermarks.

    Scaling rules (evaluated in priority order):
        1. CPU   ≥ cpu_high      → scale_up
        2. Mem   ≥ mem_high      → scale_up
        3. Queue ≥ queue_high    → scale_up
        4. Rate  ≥ rate_high     → scale_up
        5. CPU   ≤ cpu_low
           AND Mem ≤ mem_low
           AND Queue ≤ queue_low
           AND Rate ≤ rate_low   → scale_down
        6. Otherwise             → maintain

    Parameters:
        min_replicas: Minimum replica count (never go below this).
        max_replicas: Maximum replica count (never go above this).
        current_replicas: Starting replica count.
        cpu_high / cpu_low: CPU scale-up / scale-down watermarks.
        mem_high / mem_low: Memory scale-up / scale-down watermarks.
        queue_high / queue_low: Queue depth watermarks.
        rate_high / rate_low: Request rate watermarks.
        scale_up_step: Replicas to add per scale-up decision.
        scale_down_step: Replicas to remove per scale-down decision.
    """

    def __init__(
        self,
        *,
        min_replicas: int = 1,
        max_replicas: int = 10,
        current_replicas: int = 1,
        cpu_high: float = 0.80,
        cpu_low: float = 0.30,
        mem_high: float = 0.85,
        mem_low: float = 0.40,
        queue_high: int = 50,
        queue_low: int = 5,
        rate_high: float = 100.0,
        rate_low: float = 10.0,
        scale_up_step: int = 1,
        scale_down_step: int = 1,
    ) -> None:
        if min_replicas < 1:
            raise ValueError("min_replicas must be >= 1")
        if max_replicas < min_replicas:
            raise ValueError("max_replicas must be >= min_replicas")
        if not (1 <= current_replicas <= max_replicas):
            raise ValueError(
                f"current_replicas must be in [{min_replicas}, {max_replicas}]"
            )
        self._min = min_replicas
        self._max = max_replicas
        self._replicas = current_replicas
        self._cpu_high = cpu_high
        self._cpu_low = cpu_low
        self._mem_high = mem_high
        self._mem_low = mem_low
        self._queue_high = queue_high
        self._queue_low = queue_low
        self._rate_high = rate_high
        self._rate_low = rate_low
        self._up_step = scale_up_step
        self._down_step = scale_down_step

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, metrics: ScalingMetrics) -> ScalingDecision:
        """Evaluate metrics and return a ``ScalingDecision``."""
        # Scale-up rules (highest priority first)
        if metrics.cpu_usage >= self._cpu_high:
            return self._scale_up(
                trigger="cpu",
                reason=f"CPU usage {metrics.cpu_usage:.0%} >= threshold {self._cpu_high:.0%}",
                confidence=min(1.0, metrics.cpu_usage / self._cpu_high),
            )

        if metrics.memory_usage >= self._mem_high:
            return self._scale_up(
                trigger="memory",
                reason=f"Memory usage {metrics.memory_usage:.0%} >= threshold {self._mem_high:.0%}",
                confidence=min(1.0, metrics.memory_usage / self._mem_high),
            )

        if metrics.queue_depth >= self._queue_high:
            return self._scale_up(
                trigger="queue_depth",
                reason=f"Queue depth {metrics.queue_depth} >= threshold {self._queue_high}",
                confidence=min(1.0, metrics.queue_depth / max(1, self._queue_high)),
            )

        if metrics.request_rate >= self._rate_high:
            return self._scale_up(
                trigger="request_rate",
                reason=f"Request rate {metrics.request_rate:.1f}/s >= threshold {self._rate_high:.1f}/s",
                confidence=min(1.0, metrics.request_rate / max(0.001, self._rate_high)),
            )

        # Scale-down rule: ALL dimensions below low watermarks
        below_all = (
            metrics.cpu_usage <= self._cpu_low
            and metrics.memory_usage <= self._mem_low
            and metrics.queue_depth <= self._queue_low
            and metrics.request_rate <= self._rate_low
        )
        if below_all and self._replicas > self._min:
            return self._scale_down(
                reason="All metrics below low watermarks",
                confidence=0.8,
            )

        return ScalingDecision(
            action="maintain",
            replicas=self._replicas,
            reason="Metrics within normal operating range",
            confidence=1.0,
        )

    def set_thresholds(
        self,
        *,
        cpu_high: float | None = None,
        cpu_low: float | None = None,
        mem_high: float | None = None,
        mem_low: float | None = None,
    ) -> None:
        """Update watermark thresholds at runtime."""
        if cpu_high is not None:
            self._cpu_high = cpu_high
        if cpu_low is not None:
            self._cpu_low = cpu_low
        if mem_high is not None:
            self._mem_high = mem_high
        if mem_low is not None:
            self._mem_low = mem_low

    def set_replicas(self, count: int) -> None:
        """Manually override the current replica count (e.g. after a deploy)."""
        if not (self._min <= count <= self._max):
            raise ValueError(
                f"count must be in [{self._min}, {self._max}]"
            )
        self._replicas = count

    @property
    def current_replicas(self) -> int:
        return self._replicas

    @property
    def min_replicas(self) -> int:
        return self._min

    @property
    def max_replicas(self) -> int:
        return self._max

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _scale_up(self, *, trigger: str, reason: str, confidence: float) -> ScalingDecision:
        new_count = min(self._replicas + self._up_step, self._max)
        if new_count == self._replicas:
            return ScalingDecision(
                action="maintain",
                replicas=self._replicas,
                reason=f"Already at max_replicas ({self._max}); cannot scale up",
                confidence=confidence,
                trigger=trigger,
            )
        self._replicas = new_count
        return ScalingDecision(
            action="scale_up",
            replicas=new_count,
            reason=reason,
            confidence=confidence,
            trigger=trigger,
        )

    def _scale_down(self, *, reason: str, confidence: float) -> ScalingDecision:
        new_count = max(self._replicas - self._down_step, self._min)
        self._replicas = new_count
        return ScalingDecision(
            action="scale_down",
            replicas=new_count,
            reason=reason,
            confidence=confidence,
            trigger="all_low",
        )
