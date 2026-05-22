"""
WorkflowRecommender — suggests the best workflow types based on historical outcomes.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WorkflowOutcome:
    """A single recorded execution outcome for a workflow type."""

    workflow_type: str
    success: bool
    duration: float   # seconds; must be >= 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowRecommendation:
    """A recommendation for a particular workflow type."""

    recommendation_id: str
    workflow_type: str
    reason: str
    confidence: float   # 0.0 – 1.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "recommendation_id": self.recommendation_id,
            "workflow_type": self.workflow_type,
            "reason": self.reason,
            "confidence": self.confidence,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Recommender
# ---------------------------------------------------------------------------

class WorkflowRecommender:
    """
    Learns from workflow outcomes and recommends workflow types to use.

    Scoring formula (per workflow type):
        score = success_rate * 0.7 + speed_score * 0.3

    Where:
        success_rate = successful_runs / total_runs
        speed_score  = 1.0 / (1.0 + avg_duration)   (higher is faster)

    Recommendations are returned sorted by score descending.
    Confidence == score.
    """

    def __init__(self) -> None:
        # workflow_type -> list of outcomes
        self._outcomes: dict[str, list[WorkflowOutcome]] = defaultdict(list)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_outcome(
        self,
        workflow_type: str,
        success: bool,
        duration: float,
        metadata: dict[str, Any] | None = None,
    ) -> WorkflowOutcome:
        """Record the result of executing *workflow_type*."""
        if duration < 0:
            raise ValueError("duration must be >= 0")
        outcome = WorkflowOutcome(
            workflow_type=workflow_type,
            success=success,
            duration=duration,
            metadata=metadata or {},
        )
        self._outcomes[workflow_type].append(outcome)
        return outcome

    # ------------------------------------------------------------------
    # Recommendation
    # ------------------------------------------------------------------

    def recommend(
        self,
        context: dict[str, Any] | None = None,
        top_n: int = 5,
    ) -> list[WorkflowRecommendation]:
        """
        Return up to *top_n* workflow recommendations sorted by score (best first).
        *context* is reserved for future filtering (currently unused).
        """
        recommendations: list[WorkflowRecommendation] = []
        for wtype, outcomes in self._outcomes.items():
            score = self._score(outcomes)
            reason = self._reason(outcomes)
            recommendations.append(
                WorkflowRecommendation(
                    recommendation_id=uuid.uuid4().hex,
                    workflow_type=wtype,
                    reason=reason,
                    confidence=round(score, 4),
                )
            )
        recommendations.sort(key=lambda r: r.confidence, reverse=True)
        return recommendations[:top_n]

    def top_workflows(self, n: int = 3) -> list[str]:
        """Return the names of the top-*n* recommended workflow types."""
        return [r.workflow_type for r in self.recommend(top_n=n)]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def workflow_type_count(self) -> int:
        return len(self._outcomes)

    def outcome_count(self, workflow_type: str | None = None) -> int:
        if workflow_type is None:
            return sum(len(v) for v in self._outcomes.values())
        return len(self._outcomes.get(workflow_type, []))

    def success_rate(self, workflow_type: str) -> float:
        """Return the success rate for a specific workflow type, or 0.0 if unknown."""
        outcomes = self._outcomes.get(workflow_type, [])
        if not outcomes:
            return 0.0
        return sum(1 for o in outcomes if o.success) / len(outcomes)

    def average_duration(self, workflow_type: str) -> float:
        """Return the average duration for a specific workflow type, or 0.0 if unknown."""
        outcomes = self._outcomes.get(workflow_type, [])
        if not outcomes:
            return 0.0
        return sum(o.duration for o in outcomes) / len(outcomes)

    def clear(self) -> None:
        self._outcomes.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _score(self, outcomes: list[WorkflowOutcome]) -> float:
        success_rate = sum(1 for o in outcomes if o.success) / len(outcomes)
        avg_dur = sum(o.duration for o in outcomes) / len(outcomes)
        speed_score = 1.0 / (1.0 + avg_dur)
        return success_rate * 0.7 + speed_score * 0.3

    @staticmethod
    def _reason(outcomes: list[WorkflowOutcome]) -> str:
        total = len(outcomes)
        successes = sum(1 for o in outcomes if o.success)
        rate = successes / total
        return f"{successes}/{total} successful runs ({rate:.0%} success rate)"
