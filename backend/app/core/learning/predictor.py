"""
WorkflowPredictor — predicts next actions and execution risks from observed transitions.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StateTransition:
    """A single observed (state, action) → next_state transition."""

    from_state: str
    action: str
    to_state: str
    success: bool
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "from_state": self.from_state,
            "action": self.action,
            "to_state": self.to_state,
            "success": self.success,
            "metadata": self.metadata,
        }


@dataclass
class ActionPrediction:
    """Predicted next action with confidence."""

    action: str
    confidence: float   # 0.0 – 1.0
    from_state: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "confidence": self.confidence,
            "from_state": self.from_state,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Predictor
# ---------------------------------------------------------------------------

class WorkflowPredictor:
    """
    Frequency-based predictor that learns from observed state transitions.

    Prediction:
        For a given state, count how many times each action was taken.
        Predict the action with the highest frequency.
        Confidence = count(best) / total_transitions_from_state.

    Risk prediction:
        failure_rate(state, action) = failed_count / total_count.
    """

    def __init__(self) -> None:
        self._transitions: list[StateTransition] = []
        # (from_state, action) -> {"total": int, "success": int}
        self._stats: dict[tuple[str, str], dict[str, int]] = defaultdict(
            lambda: {"total": 0, "success": 0}
        )
        # from_state -> {action: count}
        self._action_counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_transition(
        self,
        from_state: str,
        action: str,
        to_state: str,
        success: bool,
        metadata: dict[str, Any] | None = None,
    ) -> StateTransition:
        """Record an observed state transition."""
        tr = StateTransition(
            from_state=from_state,
            action=action,
            to_state=to_state,
            success=success,
            metadata=metadata or {},
        )
        self._transitions.append(tr)
        key = (from_state, action)
        self._stats[key]["total"] += 1
        if success:
            self._stats[key]["success"] += 1
        self._action_counts[from_state][action] += 1
        return tr

    # ------------------------------------------------------------------
    # Prediction
    # ------------------------------------------------------------------

    def predict_next_action(self, state: str) -> ActionPrediction | None:
        """
        Return the most frequently taken action from *state*, or None if unknown.
        """
        counts = self._action_counts.get(state)
        if not counts:
            return None
        total = sum(counts.values())
        best_action = max(counts, key=lambda a: counts[a])
        confidence = counts[best_action] / total
        return ActionPrediction(
            action=best_action,
            confidence=confidence,
            from_state=state,
        )

    def predict_risk(self, state: str, action: str) -> float:
        """
        Return the estimated failure rate for (state, action). 0.0 = never fails, 1.0 = always fails.
        Returns 0.5 for unseen (state, action) pairs.
        """
        key = (state, action)
        if key not in self._stats or self._stats[key]["total"] == 0:
            return 0.5
        stats = self._stats[key]
        return 1.0 - (stats["success"] / stats["total"])

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def transition_count(self) -> int:
        return len(self._transitions)

    def known_states(self) -> list[str]:
        return list(self._action_counts.keys())

    def get_transitions(self, from_state: str | None = None) -> list[StateTransition]:
        if from_state is None:
            return list(self._transitions)
        return [t for t in self._transitions if t.from_state == from_state]

    def clear(self) -> None:
        self._transitions.clear()
        self._stats.clear()
        self._action_counts.clear()
