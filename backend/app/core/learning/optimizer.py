"""
BehaviorOptimizer — updates strategy weights based on reward signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .feedback import FeedbackEntry


# Default weight for any unseen (agent_type, action_type) pair
_DEFAULT_WEIGHT = 0.5
# Learning rate for weight updates
_ALPHA = 0.1


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class BehaviorWeight:
    """Stores the learned weight for a (agent_type, action_type) pair."""

    agent_type: str
    action_type: str
    weight: float = _DEFAULT_WEIGHT  # 0.0 – 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_type": self.agent_type,
            "action_type": self.action_type,
            "weight": self.weight,
        }


# ---------------------------------------------------------------------------
# Optimizer
# ---------------------------------------------------------------------------

class BehaviorOptimizer:
    """
    Simple reinforcement-style optimizer that nudges action weights
    toward high-reward signals and away from low-reward signals.

    Weight update rule (online, per reward sample):
        w ← w + alpha * (reward - w)
    This is equivalent to an exponential moving average toward the reward.
    """

    def __init__(self, alpha: float = _ALPHA) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        # (agent_type, action_type) -> BehaviorWeight
        self._weights: dict[tuple[str, str], BehaviorWeight] = {}

    # ------------------------------------------------------------------
    # Weight management
    # ------------------------------------------------------------------

    def _key(self, agent_type: str, action_type: str) -> tuple[str, str]:
        return (agent_type, action_type)

    def get_weight(self, agent_type: str, action_type: str) -> float:
        """Return the current weight for an (agent_type, action_type) pair."""
        key = self._key(agent_type, action_type)
        if key not in self._weights:
            return _DEFAULT_WEIGHT
        return self._weights[key].weight

    def update_weight(self, agent_type: str, action_type: str, reward: float) -> float:
        """
        Apply one online update step. Returns the new weight.

        reward : float in [0, 1]
        """
        if not (0.0 <= reward <= 1.0):
            raise ValueError("reward must be in [0.0, 1.0]")
        key = self._key(agent_type, action_type)
        if key not in self._weights:
            self._weights[key] = BehaviorWeight(agent_type=agent_type, action_type=action_type)
        bw = self._weights[key]
        bw.weight = bw.weight + self.alpha * (reward - bw.weight)
        bw.weight = max(0.0, min(1.0, bw.weight))
        return bw.weight

    # ------------------------------------------------------------------
    # Batch optimization from feedback entries
    # ------------------------------------------------------------------

    def optimize(
        self,
        feedback_entries: Iterable[FeedbackEntry],
        action_type: str = "default",
    ) -> None:
        """
        Run a batch of weight updates from feedback entries.
        Uses entry.agent_id as agent_type and *action_type* as the action key.
        """
        for entry in feedback_entries:
            self.update_weight(entry.agent_id, action_type, entry.score)

    # ------------------------------------------------------------------
    # Decision support
    # ------------------------------------------------------------------

    def best_action(self, agent_type: str, actions: list[str]) -> str | None:
        """
        Return the action with the highest learned weight for *agent_type*.
        Falls back to the first action if none are known.
        """
        if not actions:
            return None
        return max(actions, key=lambda a: self.get_weight(agent_type, a))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def weight_count(self) -> int:
        return len(self._weights)

    def get_all_weights(self) -> list[BehaviorWeight]:
        return list(self._weights.values())

    def reset(self) -> None:
        """Clear all learned weights."""
        self._weights.clear()
