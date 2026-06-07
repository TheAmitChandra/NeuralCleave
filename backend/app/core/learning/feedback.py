"""
FeedbackCollector and RewardCalculator — capture and score agent feedback.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class FeedbackEntry:
    """A single piece of feedback for an agent action."""

    entry_id: str
    agent_id: str
    task_id: str
    feedback_type: str  # "explicit" | "implicit"
    score: float  # 0.0 – 1.0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "feedback_type": self.feedback_type,
            "score": self.score,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Reward Calculator
# ---------------------------------------------------------------------------


class RewardCalculator:
    """
    Converts execution and validation outcomes into a normalised reward score.

    Score = success_weight * success_flag
           + accuracy_weight * (validation confidence, if available)
           - penalty_weight * (issues count from validation, if available)
    Clamped to [0.0, 1.0].
    """

    def __init__(
        self,
        success_weight: float = 0.6,
        accuracy_weight: float = 0.3,
        penalty_weight: float = 0.1,
    ) -> None:
        self.success_weight = success_weight
        self.accuracy_weight = accuracy_weight
        self.penalty_weight = penalty_weight

    def calculate(self, execution_result: Any, validation_result: Any | None = None) -> float:
        """
        Parameters
        ----------
        execution_result : object with `.success: bool`
        validation_result : optional object with `.confidence: float` and `.issues: list`
        """
        success_score = self.success_weight if getattr(execution_result, "success", False) else 0.0

        if validation_result is not None:
            confidence = float(getattr(validation_result, "confidence", 0.5))
            issues = getattr(validation_result, "issues", [])
            accuracy_score = self.accuracy_weight * confidence
            penalty = self.penalty_weight * len(issues)
        else:
            accuracy_score = self.accuracy_weight * 0.5
            penalty = 0.0

        raw = success_score + accuracy_score - penalty
        return max(0.0, min(1.0, raw))


# ---------------------------------------------------------------------------
# Feedback Collector
# ---------------------------------------------------------------------------


class FeedbackCollector:
    """Collects and queries feedback entries for agents and tasks."""

    VALID_TYPES = {"explicit", "implicit"}

    def __init__(self) -> None:
        self._entries: list[FeedbackEntry] = []

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        agent_id: str,
        task_id: str,
        score: float,
        feedback_type: str = "implicit",
        metadata: dict[str, Any] | None = None,
    ) -> FeedbackEntry:
        """Create and store a new FeedbackEntry."""
        if feedback_type not in self.VALID_TYPES:
            raise ValueError(f"feedback_type must be one of {self.VALID_TYPES}")
        if not (0.0 <= score <= 1.0):
            raise ValueError("score must be in [0.0, 1.0]")

        entry = FeedbackEntry(
            entry_id=uuid.uuid4().hex,
            agent_id=agent_id,
            task_id=task_id,
            feedback_type=feedback_type,
            score=score,
            metadata=metadata or {},
        )
        self._entries.append(entry)
        return entry

    # ------------------------------------------------------------------
    # Querying
    # ------------------------------------------------------------------

    def get_feedback(
        self,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> list[FeedbackEntry]:
        """Return entries optionally filtered by agent_id and/or task_id."""
        results = self._entries
        if agent_id is not None:
            results = [e for e in results if e.agent_id == agent_id]
        if task_id is not None:
            results = [e for e in results if e.task_id == task_id]
        return list(results)

    def average_score(self, agent_id: str | None = None) -> float:
        """Return the mean feedback score, optionally for a specific agent."""
        entries = self.get_feedback(agent_id=agent_id)
        if not entries:
            return 0.0
        return sum(e.score for e in entries) / len(entries)

    @property
    def entry_count(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()
