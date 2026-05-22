"""Tests for AutoScaler and scaling dataclasses."""

from __future__ import annotations

import pytest

from app.core.infrastructure.autoscaler import (
    AutoScaler,
    ScalingDecision,
    ScalingMetrics,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def low_metrics() -> ScalingMetrics:
    """All metrics well below low watermarks."""
    return ScalingMetrics(cpu_usage=0.10, memory_usage=0.15, request_rate=5.0, queue_depth=2)


def high_cpu_metrics() -> ScalingMetrics:
    return ScalingMetrics(cpu_usage=0.90, memory_usage=0.40, request_rate=20.0, queue_depth=3)


def normal_metrics() -> ScalingMetrics:
    return ScalingMetrics(cpu_usage=0.50, memory_usage=0.55, request_rate=50.0, queue_depth=20)


# ===========================================================================
# TestScalingMetrics
# ===========================================================================

class TestScalingMetrics:
    def test_valid_creation(self) -> None:
        m = ScalingMetrics(cpu_usage=0.5, memory_usage=0.6, request_rate=50.0, queue_depth=10)
        assert m.cpu_usage == 0.5

    def test_cpu_usage_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="cpu_usage"):
            ScalingMetrics(cpu_usage=1.5)

    def test_memory_usage_out_of_range_raises(self) -> None:
        with pytest.raises(ValueError, match="memory_usage"):
            ScalingMetrics(memory_usage=-0.1)

    def test_negative_request_rate_raises(self) -> None:
        with pytest.raises(ValueError, match="request_rate"):
            ScalingMetrics(request_rate=-1.0)

    def test_negative_queue_depth_raises(self) -> None:
        with pytest.raises(ValueError, match="queue_depth"):
            ScalingMetrics(queue_depth=-5)

    def test_to_dict(self) -> None:
        m = ScalingMetrics(cpu_usage=0.5, memory_usage=0.4, request_rate=30.0, queue_depth=8)
        d = m.to_dict()
        assert d["cpu_usage"] == 0.5
        assert d["queue_depth"] == 8


# ===========================================================================
# TestScalingDecision
# ===========================================================================

class TestScalingDecision:
    def test_valid_scale_up(self) -> None:
        d = ScalingDecision(action="scale_up", replicas=3, reason="high cpu")
        assert d.action == "scale_up"

    def test_invalid_action_raises(self) -> None:
        with pytest.raises(ValueError, match="action"):
            ScalingDecision(action="explode", replicas=3, reason="x")

    def test_replicas_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="replicas"):
            ScalingDecision(action="maintain", replicas=0, reason="x")

    def test_to_dict(self) -> None:
        d = ScalingDecision(action="scale_down", replicas=2, reason="low load",
                            confidence=0.8, trigger="all_low")
        dd = d.to_dict()
        assert dd["action"] == "scale_down"
        assert dd["trigger"] == "all_low"
        assert dd["confidence"] == 0.8


# ===========================================================================
# TestAutoScalerInit
# ===========================================================================

class TestAutoScalerInit:
    def test_default_properties(self) -> None:
        s = AutoScaler()
        assert s.min_replicas == 1
        assert s.max_replicas == 10
        assert s.current_replicas == 1

    def test_custom_init(self) -> None:
        s = AutoScaler(min_replicas=2, max_replicas=8, current_replicas=3)
        assert s.current_replicas == 3

    def test_min_replicas_zero_raises(self) -> None:
        with pytest.raises(ValueError, match="min_replicas"):
            AutoScaler(min_replicas=0)

    def test_max_less_than_min_raises(self) -> None:
        with pytest.raises(ValueError, match="max_replicas"):
            AutoScaler(min_replicas=5, max_replicas=2)

    def test_current_above_max_raises(self) -> None:
        with pytest.raises(ValueError):
            AutoScaler(min_replicas=1, max_replicas=3, current_replicas=5)


# ===========================================================================
# TestAutoScalerScaleUp
# ===========================================================================

class TestAutoScalerScaleUp:
    def test_high_cpu_triggers_scale_up(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=2)
        d = s.evaluate(high_cpu_metrics())
        assert d.action == "scale_up"
        assert d.trigger == "cpu"

    def test_high_cpu_increases_replicas(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=2)
        d = s.evaluate(high_cpu_metrics())
        assert d.replicas == 3

    def test_high_memory_triggers_scale_up(self) -> None:
        s = AutoScaler()
        m = ScalingMetrics(cpu_usage=0.5, memory_usage=0.90, request_rate=20.0, queue_depth=5)
        d = s.evaluate(m)
        assert d.action == "scale_up"
        assert d.trigger == "memory"

    def test_high_queue_triggers_scale_up(self) -> None:
        s = AutoScaler()
        m = ScalingMetrics(cpu_usage=0.2, memory_usage=0.3, request_rate=10.0, queue_depth=60)
        d = s.evaluate(m)
        assert d.action == "scale_up"
        assert d.trigger == "queue_depth"

    def test_high_request_rate_triggers_scale_up(self) -> None:
        s = AutoScaler()
        m = ScalingMetrics(cpu_usage=0.2, memory_usage=0.3, request_rate=150.0, queue_depth=5)
        d = s.evaluate(m)
        assert d.action == "scale_up"
        assert d.trigger == "request_rate"

    def test_cannot_exceed_max_replicas(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=3, current_replicas=3)
        d = s.evaluate(high_cpu_metrics())
        assert d.action == "maintain"
        assert d.replicas == 3

    def test_scale_up_confidence_gte_one_at_high_cpu(self) -> None:
        s = AutoScaler(cpu_high=0.8)
        m = ScalingMetrics(cpu_usage=0.95)
        d = s.evaluate(m)
        assert d.confidence >= 1.0

    def test_scale_up_step_two(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=10, current_replicas=2, scale_up_step=2)
        d = s.evaluate(high_cpu_metrics())
        assert d.replicas == 4


# ===========================================================================
# TestAutoScalerScaleDown
# ===========================================================================

class TestAutoScalerScaleDown:
    def test_all_low_triggers_scale_down(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=3)
        d = s.evaluate(low_metrics())
        assert d.action == "scale_down"
        assert d.replicas == 2

    def test_cannot_go_below_min_replicas(self) -> None:
        s = AutoScaler(min_replicas=2, max_replicas=5, current_replicas=2)
        d = s.evaluate(low_metrics())
        assert d.action == "maintain"
        assert d.replicas == 2

    def test_partial_low_does_not_scale_down(self) -> None:
        """If one metric is not low, do not scale down."""
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=3)
        m = ScalingMetrics(cpu_usage=0.1, memory_usage=0.1, request_rate=5.0, queue_depth=60)
        d = s.evaluate(m)
        assert d.action != "scale_down"


# ===========================================================================
# TestAutoScalerMaintain
# ===========================================================================

class TestAutoScalerMaintain:
    def test_normal_metrics_maintain(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=2)
        d = s.evaluate(normal_metrics())
        assert d.action == "maintain"

    def test_maintain_does_not_change_replicas(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=5, current_replicas=3)
        d = s.evaluate(normal_metrics())
        assert d.replicas == 3
        assert s.current_replicas == 3


# ===========================================================================
# TestAutoScalerSetters
# ===========================================================================

class TestAutoScalerSetters:
    def test_set_thresholds_updates_cpu_high(self) -> None:
        s = AutoScaler(cpu_high=0.8)
        s.set_thresholds(cpu_high=0.5)
        # Now 60% CPU should trigger scale_up
        m = ScalingMetrics(cpu_usage=0.6, memory_usage=0.2, request_rate=5.0, queue_depth=1)
        d = s.evaluate(m)
        assert d.action == "scale_up"

    def test_set_replicas_valid(self) -> None:
        s = AutoScaler(min_replicas=1, max_replicas=10, current_replicas=2)
        s.set_replicas(5)
        assert s.current_replicas == 5

    def test_set_replicas_out_of_range_raises(self) -> None:
        s = AutoScaler(min_replicas=2, max_replicas=5)
        with pytest.raises(ValueError):
            s.set_replicas(10)
