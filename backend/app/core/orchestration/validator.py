"""
validator.py — ValidatorAgent

Validates execution results against task expectations using
built-in checks and pluggable async validation rules.
"""
from __future__ import annotations

import uuid
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from app.core.orchestration.executor import ExecutionResult
from app.core.orchestration.planner import SubTask


# ---------------------------------------------------------------------------
# Type alias
# ---------------------------------------------------------------------------

ValidationRule = Callable[
    [SubTask, ExecutionResult], Awaitable[list[str]]
]


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """The outcome of validating a single execution result."""

    task_id: str
    valid: bool
    confidence: float                   # 0.0–1.0
    issues: list[str] = field(default_factory=list)
    recommendation: str = "accept"      # "accept" | "retry" | "escalate"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "valid": self.valid,
            "confidence": self.confidence,
            "issues": list(self.issues),
            "recommendation": self.recommendation,
            "metadata": dict(self.metadata),
        }


# ---------------------------------------------------------------------------
# ValidatorAgent
# ---------------------------------------------------------------------------


class ValidatorAgent:
    """Validates ExecutionResults for correctness and completeness.

    Built-in checks:
    - Execution must be successful (``result.success is True``)
    - A successful result must produce output

    Additional domain-specific checks can be injected via
    ``add_rule(async_callable)``.
    """

    def __init__(
        self,
        agent_id: str | None = None,
        confidence_threshold: float = 0.7,
    ) -> None:
        self.agent_id: str = agent_id or str(uuid.uuid4())
        self.confidence_threshold: float = confidence_threshold
        self._rules: list[ValidationRule] = []

    # ------------------------------------------------------------------
    # Rule management
    # ------------------------------------------------------------------

    def add_rule(self, rule: ValidationRule) -> None:
        """Add a custom async validation rule."""
        self._rules.append(rule)

    def remove_rule(self, rule: ValidationRule) -> None:
        """Remove a rule; silently ignore if not present."""
        with suppress(ValueError):
            self._rules.remove(rule)

    @property
    def rule_count(self) -> int:
        return len(self._rules)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate(
        self, task: SubTask, result: ExecutionResult
    ) -> ValidationResult:
        """Validate a single (task, result) pair."""
        issues: list[str] = []

        # Built-in check 1: execution must succeed
        if not result.success:
            issues.append(
                f"Task execution failed: {result.error or 'unknown error'}"
            )

        # Built-in check 2: successful result must have output
        if result.success and result.output is None:
            issues.append("Task succeeded but produced no output")

        # Custom rules
        for rule in self._rules:
            try:
                rule_issues = await rule(task, result)
                issues.extend(rule_issues)
            except Exception as exc:  # noqa: BLE001
                issues.append(f"Validation rule raised exception: {exc}")

        confidence = self._compute_confidence(result, issues)
        valid = result.success and len(issues) == 0
        recommendation = self._recommend(valid, confidence, issues)

        return ValidationResult(
            task_id=task.task_id,
            valid=valid,
            confidence=confidence,
            issues=issues,
            recommendation=recommendation,
        )

    async def validate_batch(
        self, pairs: list[tuple[SubTask, ExecutionResult]]
    ) -> list[ValidationResult]:
        """Validate multiple (task, result) pairs sequentially."""
        return [await self.validate(task, result) for task, result in pairs]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_confidence(
        self, result: ExecutionResult, issues: list[str]
    ) -> float:
        if not result.success:
            return 0.0
        if issues:
            return max(0.0, 1.0 - len(issues) * 0.2)
        return 1.0

    def _recommend(
        self, valid: bool, confidence: float, issues: list[str]
    ) -> str:
        if valid and confidence >= self.confidence_threshold:
            return "accept"
        # Low confidence or many issues → escalate
        if confidence < 0.3 or len(issues) >= 3:
            return "escalate"
        # Recoverable failures → retry
        return "retry"
