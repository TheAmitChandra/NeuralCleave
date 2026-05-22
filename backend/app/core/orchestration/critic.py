"""
critic.py — CriticAgent

Reviews execution results and validation outcomes to score
output quality. Produces per-task CritiqueScores and a
plan-level PlanCritique aggregate.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from app.core.orchestration.executor import ExecutionResult
from app.core.orchestration.planner import Plan, SubTask
from app.core.orchestration.validator import ValidationResult


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class CritiqueScore:
    """Quality assessment for a single task result."""

    task_id: str
    quality_score: float        # 0–100
    completeness: float         # 0.0–1.0
    accuracy: float             # 0.0–1.0
    issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "quality_score": self.quality_score,
            "completeness": self.completeness,
            "accuracy": self.accuracy,
            "issues": list(self.issues),
            "recommendations": list(self.recommendations),
            "metadata": dict(self.metadata),
        }


@dataclass
class PlanCritique:
    """Aggregate quality assessment across all tasks in a Plan."""

    plan_id: str
    overall_score: float
    task_scores: list[CritiqueScore] = field(default_factory=list)
    summary: str = ""
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "overall_score": self.overall_score,
            "task_scores": [s.to_dict() for s in self.task_scores],
            "summary": self.summary,
            "recommendations": list(self.recommendations),
        }


# ---------------------------------------------------------------------------
# CriticAgent
# ---------------------------------------------------------------------------


class CriticAgent:
    """Reviews task execution quality combining validation outcomes.

    Scoring model:
    - **accuracy** (60 % weight): 1.0 if valid, else ``validation.confidence``
    - **completeness** (40 % weight): inferred from output content
    - **penalty**: 5 points per distinct issue (capped)
    - Final score in [0, 100]
    """

    def __init__(
        self,
        agent_id: str | None = None,
        quality_threshold: float = 70.0,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.quality_threshold: float = quality_threshold

    # ------------------------------------------------------------------
    # Per-task critique
    # ------------------------------------------------------------------

    async def critique(
        self,
        task: SubTask,
        result: ExecutionResult,
        validation: ValidationResult,
    ) -> CritiqueScore:
        issues: list[str] = list(validation.issues)
        recommendations: list[str] = []

        accuracy = 1.0 if validation.valid else max(0.0, validation.confidence)
        completeness = self._assess_completeness(result)

        if completeness < 0.5:
            issues.append("Output is incomplete or missing")
            recommendations.append("Ensure task produces complete output")

        if not validation.valid and validation.issues:
            snippet = ", ".join(validation.issues[:2])
            recommendations.append(f"Address validation issues: {snippet}")

        if result.error:
            issues.append(f"Execution error: {result.error}")
            recommendations.append("Fix execution error before rerunning")

        quality_score = self._compute_quality(accuracy, completeness, len(issues))

        return CritiqueScore(
            task_id=task.task_id,
            quality_score=quality_score,
            completeness=completeness,
            accuracy=accuracy,
            issues=issues,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Plan-level critique
    # ------------------------------------------------------------------

    async def critique_plan(
        self,
        plan: Plan,
        results: list[ExecutionResult],
        validations: list[ValidationResult],
    ) -> PlanCritique:
        task_map = {t.task_id: t for t in plan.subtasks}
        result_map = {r.task_id: r for r in results}
        validation_map = {v.task_id: v for v in validations}

        scores: list[CritiqueScore] = []
        for task_id, task in task_map.items():
            result = result_map.get(task_id)
            validation = validation_map.get(task_id)
            if result is not None and validation is not None:
                score = await self.critique(task, result, validation)
                scores.append(score)

        overall = (
            sum(s.quality_score for s in scores) / len(scores) if scores else 0.0
        )
        # Deduplicated recommendations across all tasks
        recommendations = list({r for s in scores for r in s.recommendations})

        status = "good" if overall >= self.quality_threshold else "needs_improvement"
        summary = (
            f"Plan quality: {overall:.1f}/100 ({status}). "
            f"{len(scores)} tasks evaluated."
        )

        return PlanCritique(
            plan_id=plan.plan_id,
            overall_score=round(overall, 2),
            task_scores=scores,
            summary=summary,
            recommendations=recommendations,
        )

    # ------------------------------------------------------------------
    # Threshold check
    # ------------------------------------------------------------------

    def meets_threshold(self, score: CritiqueScore) -> bool:
        return score.quality_score >= self.quality_threshold

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _assess_completeness(self, result: ExecutionResult) -> float:
        if not result.success:
            return 0.0
        output = result.output
        if output is None:
            return 0.5
        if isinstance(output, str):
            return 1.0 if output.strip() else 0.0
        if isinstance(output, (list, dict)):
            return 1.0 if output else 0.3
        return 1.0

    def _compute_quality(
        self, accuracy: float, completeness: float, issue_count: int
    ) -> float:
        base = (accuracy * 0.6 + completeness * 0.4) * 100.0
        penalty = min(base, issue_count * 5.0)
        return round(max(0.0, base - penalty), 2)
