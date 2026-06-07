"""
Unit tests for BehaviorOptimizer and BehaviorWeight.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.core.learning.feedback import FeedbackEntry
from app.core.learning.optimizer import _ALPHA, _DEFAULT_WEIGHT, BehaviorOptimizer, BehaviorWeight

# ---------------------------------------------------------------------------
# BehaviorWeight
# ---------------------------------------------------------------------------


class TestBehaviorWeight:
    def test_default_weight(self):
        bw = BehaviorWeight(agent_type="planner", action_type="plan")
        assert bw.weight == _DEFAULT_WEIGHT

    def test_to_dict(self):
        bw = BehaviorWeight(agent_type="executor", action_type="run", weight=0.7)
        d = bw.to_dict()
        assert d["agent_type"] == "executor"
        assert d["action_type"] == "run"
        assert d["weight"] == 0.7

    def test_custom_weight(self):
        bw = BehaviorWeight("a", "b", weight=0.9)
        assert bw.weight == 0.9


# ---------------------------------------------------------------------------
# BehaviorOptimizer — construction
# ---------------------------------------------------------------------------


class TestOptimizerInit:
    def test_default_alpha(self):
        opt = BehaviorOptimizer()
        assert opt.alpha == _ALPHA

    def test_custom_alpha(self):
        opt = BehaviorOptimizer(alpha=0.2)
        assert opt.alpha == 0.2

    def test_invalid_alpha_raises(self):
        with pytest.raises(ValueError):
            BehaviorOptimizer(alpha=0.0)

    def test_initial_weight_count_zero(self):
        opt = BehaviorOptimizer()
        assert opt.weight_count == 0


# ---------------------------------------------------------------------------
# get_weight
# ---------------------------------------------------------------------------


class TestGetWeight:
    def test_default_for_unknown(self):
        opt = BehaviorOptimizer()
        assert opt.get_weight("x", "y") == _DEFAULT_WEIGHT

    def test_returns_updated_weight(self):
        opt = BehaviorOptimizer(alpha=1.0)
        opt.update_weight("planner", "plan", 0.9)
        assert opt.get_weight("planner", "plan") == pytest.approx(0.9)


# ---------------------------------------------------------------------------
# update_weight
# ---------------------------------------------------------------------------


class TestUpdateWeight:
    def test_new_pair_created(self):
        opt = BehaviorOptimizer()
        opt.update_weight("a", "b", 0.8)
        assert opt.weight_count == 1

    def test_weight_moves_toward_high_reward(self):
        opt = BehaviorOptimizer(alpha=0.5)
        opt.update_weight("a", "b", 1.0)
        w = opt.get_weight("a", "b")
        assert w > _DEFAULT_WEIGHT

    def test_weight_moves_toward_low_reward(self):
        opt = BehaviorOptimizer(alpha=0.5)
        opt.update_weight("a", "b", 0.0)
        w = opt.get_weight("a", "b")
        assert w < _DEFAULT_WEIGHT

    def test_multiple_updates_converge(self):
        opt = BehaviorOptimizer(alpha=0.3)
        for _ in range(100):
            opt.update_weight("a", "b", 1.0)
        assert opt.get_weight("a", "b") > 0.99

    def test_invalid_reward_raises(self):
        opt = BehaviorOptimizer()
        with pytest.raises(ValueError, match="reward"):
            opt.update_weight("a", "b", 1.5)

    def test_invalid_negative_reward_raises(self):
        opt = BehaviorOptimizer()
        with pytest.raises(ValueError, match="reward"):
            opt.update_weight("a", "b", -0.1)

    def test_boundary_rewards_accepted(self):
        opt = BehaviorOptimizer()
        opt.update_weight("a", "b", 0.0)
        opt.update_weight("a", "c", 1.0)
        assert opt.weight_count == 2

    def test_weight_clamped_to_one(self):
        opt = BehaviorOptimizer(alpha=1.0)
        opt.update_weight("a", "b", 1.0)
        assert opt.get_weight("a", "b") <= 1.0

    def test_weight_clamped_to_zero(self):
        opt = BehaviorOptimizer(alpha=1.0)
        opt.update_weight("a", "b", 0.0)
        assert opt.get_weight("a", "b") >= 0.0

    def test_separate_pairs_independent(self):
        opt = BehaviorOptimizer(alpha=1.0)
        opt.update_weight("a", "action1", 1.0)
        opt.update_weight("a", "action2", 0.0)
        assert opt.get_weight("a", "action1") > opt.get_weight("a", "action2")


# ---------------------------------------------------------------------------
# optimize (batch from feedback entries)
# ---------------------------------------------------------------------------


class TestOptimize:
    def _entry(self, agent_id: str, score: float) -> FeedbackEntry:
        return FeedbackEntry(
            entry_id="x",
            agent_id=agent_id,
            task_id="t",
            feedback_type="implicit",
            score=score,
        )

    def test_optimize_updates_weights(self):
        opt = BehaviorOptimizer(alpha=1.0)
        entries = [self._entry("planner", 0.9), self._entry("planner", 0.9)]
        opt.optimize(entries, action_type="plan")
        assert opt.get_weight("planner", "plan") == pytest.approx(0.9)

    def test_optimize_multiple_agents(self):
        opt = BehaviorOptimizer(alpha=1.0)
        entries = [self._entry("planner", 1.0), self._entry("executor", 0.0)]
        opt.optimize(entries, action_type="act")
        assert opt.get_weight("planner", "act") > opt.get_weight("executor", "act")

    def test_optimize_empty_entries(self):
        opt = BehaviorOptimizer()
        opt.optimize([], action_type="x")
        assert opt.weight_count == 0


# ---------------------------------------------------------------------------
# best_action
# ---------------------------------------------------------------------------


class TestBestAction:
    def test_best_action_returns_highest_weight(self):
        opt = BehaviorOptimizer(alpha=1.0)
        opt.update_weight("planner", "plan_a", 0.9)
        opt.update_weight("planner", "plan_b", 0.3)
        assert opt.best_action("planner", ["plan_a", "plan_b"]) == "plan_a"

    def test_best_action_with_unknown_actions_uses_default(self):
        opt = BehaviorOptimizer()
        # All unknown → all have default weight → any stable first max
        result = opt.best_action("agent", ["x", "y", "z"])
        assert result in ["x", "y", "z"]

    def test_best_action_single_option(self):
        opt = BehaviorOptimizer()
        assert opt.best_action("a", ["only"]) == "only"

    def test_best_action_empty_list_returns_none(self):
        opt = BehaviorOptimizer()
        assert opt.best_action("a", []) is None


# ---------------------------------------------------------------------------
# reset / introspection
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_clears_weights(self):
        opt = BehaviorOptimizer()
        opt.update_weight("a", "b", 0.8)
        opt.reset()
        assert opt.weight_count == 0

    def test_get_all_weights(self):
        opt = BehaviorOptimizer()
        opt.update_weight("a", "b", 0.5)
        opt.update_weight("c", "d", 0.7)
        weights = opt.get_all_weights()
        assert len(weights) == 2
        assert all(isinstance(w, BehaviorWeight) for w in weights)
