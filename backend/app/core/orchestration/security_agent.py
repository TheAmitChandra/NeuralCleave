"""
security_agent.py — SecurityAgent

Monitors execution risks in a Plan and individual tasks.
Assigns risk scores (0–100), categorises risk levels, and
blocks tasks that exceed the configured threshold.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.orchestration.planner import Plan, SubTask

# ---------------------------------------------------------------------------
# Constants — risk levels and their score boundaries
# ---------------------------------------------------------------------------

RISK_LEVELS: list[tuple[float, str]] = [
    (25.0, "low"),
    (60.0, "medium"),
    (85.0, "high"),
    (100.0, "critical"),
]


def _level_from_score(score: float) -> str:
    for threshold, level in RISK_LEVELS:
        if score <= threshold:
            return level
    return "critical"


# ---------------------------------------------------------------------------
# Type alias for risk-factor rules
# ---------------------------------------------------------------------------

RiskRule = Callable[[SubTask], Awaitable[tuple[float, str]]]
"""
Async callable that receives a SubTask and returns *(added_score, factor_description)*.
Return ``(0.0, "")`` to signal no risk from this rule.
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RiskAssessment:
    """Risk evaluation result for a single SubTask."""

    task_id: str
    risk_score: float  # 0–100
    risk_level: str  # "low" | "medium" | "high" | "critical"
    risk_factors: list[str] = field(default_factory=list)
    blocked: bool = False
    recommendation: str = "proceed"  # "proceed" | "review" | "block"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "risk_factors": list(self.risk_factors),
            "blocked": self.blocked,
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }


@dataclass
class PlanRiskReport:
    """Aggregate risk report for an entire Plan."""

    plan_id: str
    assessments: list[RiskAssessment] = field(default_factory=list)
    overall_risk_score: float = 0.0
    blocked_count: int = 0
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "assessments": [a.to_dict() for a in self.assessments],
            "overall_risk_score": self.overall_risk_score,
            "blocked_count": self.blocked_count,
            "summary": self.summary,
        }


# ---------------------------------------------------------------------------
# SecurityAgent
# ---------------------------------------------------------------------------


class SecurityAgent:
    """Evaluates SubTasks for security risks.

    Built-in risk heuristics:
    - Keyword scanning in description (``delete``, ``drop``, ``rm``, ``sudo``,
      ``exec``, ``eval``, ``shell``, ``chmod``, ``format``) — 15 pts each, max 45
    - ``payload["risk_score"]`` override — used directly if provided
    - High-priority tasks (priority ≤ 2) — extra 5 pts

    Additional domain-specific rules can be injected via ``add_rule``.
    """

    _RISK_KEYWORDS: dict[str, float] = {
        "delete": 15.0,
        "drop": 15.0,
        "remove": 10.0,
        "rm ": 15.0,
        "sudo": 15.0,
        "exec": 15.0,
        "eval": 15.0,
        "shell": 10.0,
        "chmod": 15.0,
        "format": 15.0,
        "truncate": 15.0,
        "overwrite": 10.0,
    }

    def __init__(
        self,
        agent_id: str | None = None,
        block_threshold: float = 85.0,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.block_threshold: float = block_threshold
        self._rules: list[RiskRule] = []

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: RiskRule) -> None:
        self._rules.append(rule)

    def remove_rule(self, rule: RiskRule) -> None:
        try:
            self._rules.remove(rule)
        except ValueError:
            pass

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ------------------------------------------------------------------
    # Assessment
    # ------------------------------------------------------------------

    async def assess(self, task: SubTask) -> RiskAssessment:
        """Compute a RiskAssessment for a single SubTask."""
        factors: list[str] = []
        score: float = 0.0

        # Payload override
        payload_score = task.payload.get("risk_score")
        if payload_score is not None:
            score = float(payload_score)
            factors.append(f"payload risk_score override: {score}")
        else:
            # Built-in keyword scan
            desc_lower = task.description.lower()
            kw_score: float = 0.0
            for keyword, pts in self._RISK_KEYWORDS.items():
                if keyword in desc_lower:
                    kw_score += pts
                    factors.append(f"dangerous keyword: '{keyword.strip()}'")
            score += min(kw_score, 45.0)  # cap keyword contribution

            # High-priority boost
            if task.priority <= 2:
                score += 5.0
                factors.append("high-priority task bonus")

        # Custom rules
        for rule in self._rules:
            try:
                added, factor_desc = await rule(task)
                if added > 0:
                    score += added
                    if factor_desc:
                        factors.append(factor_desc)
            except Exception as exc:  # noqa: BLE001
                factors.append(f"risk rule error: {exc}")

        score = min(max(score, 0.0), 100.0)
        level = _level_from_score(score)
        blocked = score >= self.block_threshold
        recommendation = self._recommend(score)

        return RiskAssessment(
            task_id=task.task_id,
            risk_score=round(score, 2),
            risk_level=level,
            risk_factors=factors,
            blocked=blocked,
            recommendation=recommendation,
        )

    async def assess_plan(self, plan: Plan) -> PlanRiskReport:
        """Assess all SubTasks in a Plan and return an aggregate report."""
        assessments: list[RiskAssessment] = []
        for task in plan.subtasks:
            assessments.append(await self.assess(task))

        blocked_count = sum(1 for a in assessments if a.blocked)
        overall = sum(a.risk_score for a in assessments) / len(assessments) if assessments else 0.0
        status = "safe" if blocked_count == 0 else f"{blocked_count} task(s) blocked"
        summary = f"Plan risk: {overall:.1f}/100 — {status}. " f"{len(assessments)} tasks assessed."

        return PlanRiskReport(
            plan_id=plan.plan_id,
            assessments=assessments,
            overall_risk_score=round(overall, 2),
            blocked_count=blocked_count,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _recommend(self, score: float) -> str:
        if score >= self.block_threshold:
            return "block"
        if score >= 60.0:
            return "review"
        return "proceed"
