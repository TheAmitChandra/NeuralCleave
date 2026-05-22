"""Execution Quality Scorer — 0–100 quality score for agent outputs.

The scorer evaluates an agent action's output quality across multiple
dimensions and returns a composite ``QualityScore``.  High-quality
outputs are allowed to proceed; low-quality outputs trigger retry or
escalation.

Scoring dimensions (each 0–100, then weighted):
    completeness  — did the response address all required elements?
    relevance     — how well does the output match the original task?
    coherence     — is the output internally consistent and well-formed?
    safety        — does the output pass injection and sensitive content checks?
    efficiency    — token / time efficiency relative to task complexity
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.security.prompt_injection import PromptInjectionDetector

logger = structlog.get_logger(__name__)

_INJECTION_DETECTOR = PromptInjectionDetector()

# Default weights (must sum to 1.0)
_DEFAULT_WEIGHTS: dict[str, float] = {
    "completeness": 0.30,
    "relevance": 0.25,
    "coherence": 0.25,
    "safety": 0.15,
    "efficiency": 0.05,
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DimensionScore:
    name: str
    raw: float       # 0–100
    weight: float
    weighted: float  # raw * weight
    notes: str = ""


@dataclass
class QualityScore:
    """Composite quality score for an agent output.

    Attributes:
        total:           Weighted composite (0–100).
        grade:           A / B / C / D / F letter grade.
        dimensions:      Per-dimension breakdown.
        pass_threshold:  Minimum score to pass (caller-configurable).
        passed:          True if total ≥ pass_threshold.
        recommendation:  ``"pass" | "retry" | "rethink" | "escalate"``.
        details:         Extra diagnostic data.
    """

    total: float
    grade: str
    dimensions: list[DimensionScore]
    pass_threshold: float
    passed: bool
    recommendation: str
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class ExecutionScorer:
    """Score the quality of an agent execution output.

    Parameters:
        pass_threshold:  Score (0–100) required to mark output as passing.
        weights:         Custom dimension weights (must sum to 1.0).
    """

    def __init__(
        self,
        pass_threshold: float = 60.0,
        weights: dict[str, float] | None = None,
    ) -> None:
        self._pass_threshold = pass_threshold
        self._weights = weights or _DEFAULT_WEIGHTS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def score(
        self,
        *,
        task_description: str,
        output: str,
        expected_elements: list[str] | None = None,
        execution_time_seconds: float | None = None,
        max_expected_seconds: float = 30.0,
    ) -> QualityScore:
        """Compute a quality score for ``output`` relative to ``task_description``.

        Parameters:
            task_description:     Original task text the agent was given.
            output:               Agent's generated output (text).
            expected_elements:    Optional list of strings that should appear in output.
            execution_time_seconds: Actual wall-clock time (for efficiency scoring).
            max_expected_seconds: Reference ceiling for efficiency scoring.

        Returns:
            ``QualityScore``.
        """
        dims: list[DimensionScore] = []

        # --- Completeness ---
        comp_raw = self._score_completeness(output, expected_elements)
        dims.append(DimensionScore(
            name="completeness",
            raw=comp_raw,
            weight=self._weights.get("completeness", 0.30),
            weighted=comp_raw * self._weights.get("completeness", 0.30),
        ))

        # --- Relevance ---
        rel_raw = self._score_relevance(task_description, output)
        dims.append(DimensionScore(
            name="relevance",
            raw=rel_raw,
            weight=self._weights.get("relevance", 0.25),
            weighted=rel_raw * self._weights.get("relevance", 0.25),
        ))

        # --- Coherence ---
        coh_raw = self._score_coherence(output)
        dims.append(DimensionScore(
            name="coherence",
            raw=coh_raw,
            weight=self._weights.get("coherence", 0.25),
            weighted=coh_raw * self._weights.get("coherence", 0.25),
        ))

        # --- Safety ---
        safe_raw = self._score_safety(output)
        dims.append(DimensionScore(
            name="safety",
            raw=safe_raw,
            weight=self._weights.get("safety", 0.15),
            weighted=safe_raw * self._weights.get("safety", 0.15),
        ))

        # --- Efficiency ---
        eff_raw = self._score_efficiency(execution_time_seconds, max_expected_seconds)
        dims.append(DimensionScore(
            name="efficiency",
            raw=eff_raw,
            weight=self._weights.get("efficiency", 0.05),
            weighted=eff_raw * self._weights.get("efficiency", 0.05),
        ))

        total = round(sum(d.weighted for d in dims), 2)
        grade = self._grade(total)
        passed = total >= self._pass_threshold
        recommendation = self._recommend(total)

        logger.info(
            "scorer.scored",
            total=total,
            grade=grade,
            passed=passed,
            recommendation=recommendation,
        )

        return QualityScore(
            total=total,
            grade=grade,
            dimensions=dims,
            pass_threshold=self._pass_threshold,
            passed=passed,
            recommendation=recommendation,
            details={
                "output_length": len(output),
                "task_length": len(task_description),
                "execution_time_seconds": execution_time_seconds,
            },
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_completeness(
        self, output: str, expected_elements: list[str] | None
    ) -> float:
        """Return 0–100 based on how many expected elements appear in output."""
        if not expected_elements:
            # Fall back to length heuristic
            words = len(output.split())
            return min(words / 50.0 * 100, 100.0)

        output_lower = output.lower()
        found = sum(1 for el in expected_elements if el.lower() in output_lower)
        return (found / len(expected_elements)) * 100.0

    def _score_relevance(self, task: str, output: str) -> float:
        """Token overlap between task keywords and output."""
        task_tokens = set(re.findall(r"\b\w{4,}\b", task.lower()))
        output_tokens = set(re.findall(r"\b\w{4,}\b", output.lower()))
        if not task_tokens:
            return 70.0  # no task context → neutral
        overlap = len(task_tokens & output_tokens) / len(task_tokens)
        return round(min(overlap * 150, 100.0), 2)  # amplify slightly

    def _score_coherence(self, output: str) -> float:
        """Heuristic: penalise very short, very fragmented, or malformed output."""
        if not output.strip():
            return 0.0

        sentences = re.split(r"[.!?]+", output)
        non_empty = [s.strip() for s in sentences if s.strip()]
        sentence_count = len(non_empty)
        word_count = len(output.split())

        score = 100.0

        # Too short — probably incomplete
        if word_count < 5:
            score -= 50.0
        elif word_count < 15:
            score -= 20.0

        # Highly repetitive output
        unique_words = len(set(output.lower().split()))
        if word_count > 0:
            uniqueness = unique_words / word_count
            if uniqueness < 0.3:
                score -= 30.0
            elif uniqueness < 0.5:
                score -= 15.0

        # Single fragment with no punctuation
        if sentence_count == 1 and word_count > 20:
            score -= 10.0

        return max(score, 0.0)

    def _score_safety(self, output: str) -> float:
        """Run injection scan on the output; penalise if patterns match."""
        result = _INJECTION_DETECTOR.scan(output, source="scorer.output")
        if result.is_injection:
            return 0.0
        if result.confidence > 0.3:
            return 50.0
        return 100.0

    def _score_efficiency(
        self, elapsed: float | None, max_expected: float
    ) -> float:
        """Return 100 if elapsed is well within budget, 0 if it massively exceeds it."""
        if elapsed is None:
            return 80.0  # unknown → generous default
        if elapsed <= 0:
            return 100.0
        ratio = elapsed / max(max_expected, 1.0)
        if ratio <= 0.5:
            return 100.0
        if ratio <= 1.0:
            return 80.0
        if ratio <= 2.0:
            return 50.0
        return max(100.0 - ratio * 20, 0.0)

    # ------------------------------------------------------------------
    # Grade / recommendation
    # ------------------------------------------------------------------

    def _grade(self, score: float) -> str:
        if score >= 90:
            return "A"
        if score >= 75:
            return "B"
        if score >= 60:
            return "C"
        if score >= 40:
            return "D"
        return "F"

    def _recommend(self, score: float) -> str:
        if score >= self._pass_threshold:
            return "pass"
        if score >= 45:
            return "retry"
        if score >= 25:
            return "rethink"
        return "escalate"
