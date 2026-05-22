"""Reflection Engine — meta-cognitive evaluation loop for CortexFlow.

The engine sits between an agent's action executor and its next iteration.
After each action, ``ReflectionEngine.reflect()`` is called with the raw
output and context.  It:

1. Scores execution quality via ``ExecutionScorer``
2. Detects hallucination signals via ``HallucinationDetector``
3. Combines both into a ``ReflectionResult`` with a single recommendation

Decision matrix
───────────────
quality ≥ pass_threshold AND hallucination_score < 0.5  → **pass**
quality ≥ pass_threshold AND hallucination_score ≥ 0.5  → **rethink**
quality < pass_threshold AND quality ≥ 45               → **retry**
quality < 45              AND hallucination_score < 0.5  → **rethink**
quality < 45              AND hallucination_score ≥ 0.5  → **escalate**

Usage::

    engine = ReflectionEngine()
    result = await engine.reflect(
        task="Summarise the article.",
        output="The article discusses AI trends.",
        sources=["AI is evolving rapidly..."],
        execution_time_seconds=2.3,
    )
    if result.should_retry:
        # Re-invoke the tool
    elif result.should_escalate:
        # Hand off to human approval
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.reflection.hallucination import HallucinationDetector, HallucinationReport
from app.core.reflection.scorer import ExecutionScorer, QualityScore

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ReflectionResult:
    """Outcome of a reflection cycle.

    Attributes:
        quality:            Full quality score from ``ExecutionScorer``.
        hallucination:      Full hallucination report from ``HallucinationDetector``.
        recommendation:     ``"pass" | "retry" | "rethink" | "escalate"``.
        should_retry:       Shortcut — True when recommendation is ``"retry"``.
        should_escalate:    Shortcut — True when recommendation is ``"escalate"``.
        retry_delay_seconds: Suggested back-off before retry (exponential).
        insights:           Human-readable list of observations.
        metadata:           Extra diagnostics.
    """

    quality: QualityScore
    hallucination: HallucinationReport
    recommendation: str
    should_retry: bool
    should_escalate: bool
    retry_delay_seconds: float
    insights: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

class ReflectionEngine:
    """Meta-cognitive reflection engine.

    Parameters:
        quality_pass_threshold:       Minimum quality score (0–100) to pass.
        hallucination_threshold:      Maximum hallucination score (0–1) to pass.
        base_retry_delay:             Initial back-off in seconds.
        max_retry_delay:              Cap on back-off.
    """

    def __init__(
        self,
        quality_pass_threshold: float = 60.0,
        hallucination_threshold: float = 0.5,
        base_retry_delay: float = 2.0,
        max_retry_delay: float = 60.0,
    ) -> None:
        self._quality_threshold = quality_pass_threshold
        self._hallucination_threshold = hallucination_threshold
        self._base_retry_delay = base_retry_delay
        self._max_retry_delay = max_retry_delay

        self._scorer = ExecutionScorer(pass_threshold=quality_pass_threshold)
        self._hallucination_detector = HallucinationDetector(
            hallucination_threshold=hallucination_threshold
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def reflect(
        self,
        *,
        task: str,
        output: str,
        sources: list[str] | None = None,
        self_confidence: float | None = None,
        expected_elements: list[str] | None = None,
        execution_time_seconds: float | None = None,
        max_expected_seconds: float = 30.0,
        attempt_number: int = 1,
    ) -> ReflectionResult:
        """Run a full reflection cycle.

        Parameters:
            task:                     Original task description.
            output:                   Agent's text output.
            sources:                  Reference documents for hallucination checks.
            self_confidence:          LLM self-reported confidence (0–1) if available.
            expected_elements:        Strings expected in the output (completeness).
            execution_time_seconds:   Wall-clock time used.
            max_expected_seconds:     Budget for efficiency scoring.
            attempt_number:           Current attempt count (for back-off calculation).

        Returns:
            ``ReflectionResult``.
        """
        log = logger.bind(task_snippet=task[:80], attempt=attempt_number)
        log.info("reflection.start")

        # Run quality scoring and hallucination detection concurrently
        quality, hallucination = await asyncio.gather(
            asyncio.to_thread(
                self._scorer.score,
                task_description=task,
                output=output,
                expected_elements=expected_elements,
                execution_time_seconds=execution_time_seconds,
                max_expected_seconds=max_expected_seconds,
            ),
            asyncio.to_thread(
                self._hallucination_detector.analyse,
                output,
                sources=sources,
                self_confidence=self_confidence,
            ),
        )

        recommendation = self._compute_recommendation(quality, hallucination)
        insights = self._build_insights(quality, hallucination, recommendation)
        retry_delay = self._compute_retry_delay(attempt_number)

        log.info(
            "reflection.complete",
            quality_total=quality.total,
            hallucination_score=hallucination.hallucination_score,
            recommendation=recommendation,
        )

        return ReflectionResult(
            quality=quality,
            hallucination=hallucination,
            recommendation=recommendation,
            should_retry=(recommendation == "retry"),
            should_escalate=(recommendation == "escalate"),
            retry_delay_seconds=retry_delay,
            insights=insights,
            metadata={
                "attempt_number": attempt_number,
                "quality_grade": quality.grade,
                "hallucination_signals": [
                    s.signal_type for s in hallucination.signals
                ],
            },
        )

    # ------------------------------------------------------------------
    # Synchronous convenience wrapper
    # ------------------------------------------------------------------

    def reflect_sync(self, **kwargs: Any) -> ReflectionResult:  # noqa: ANN401
        """Synchronous wrapper around ``reflect`` (runs in a dedicated thread)."""
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, self.reflect(**kwargs)).result()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _compute_recommendation(
        self,
        quality: QualityScore,
        hallucination: HallucinationReport,
    ) -> str:
        """Combine quality and hallucination scores into one recommendation."""
        q = quality.total
        h = hallucination.hallucination_score

        quality_pass = q >= self._quality_threshold
        hallucination_pass = h < self._hallucination_threshold

        if quality_pass and hallucination_pass:
            return "pass"
        if quality_pass and not hallucination_pass:
            return "rethink"
        if not quality_pass and q >= 45 and hallucination_pass:
            return "retry"
        if not quality_pass and q < 25:
            if not hallucination_pass:
                return "escalate"
            return "rethink"
        # Middle range: quality insufficient but not catastrophic
        if not hallucination_pass:
            return "rethink"
        return "retry"

    def _build_insights(
        self,
        quality: QualityScore,
        hallucination: HallucinationReport,
        recommendation: str,
    ) -> list[str]:
        insights: list[str] = []

        # Quality insights
        for dim in quality.dimensions:
            if dim.raw < 40:
                insights.append(
                    f"Low {dim.name} score ({dim.raw:.0f}/100) — check output coverage."
                )
            elif dim.raw >= 90:
                insights.append(f"Excellent {dim.name} ({dim.raw:.0f}/100).")

        # Hallucination insights
        for sig in hallucination.signals:
            insights.append(
                f"Hallucination signal [{sig.signal_type}] "
                f"severity={sig.severity:.2f}: {sig.description}"
            )

        # Recommendation insight
        if recommendation == "escalate":
            insights.append(
                "Output quality and hallucination risk require human review."
            )
        elif recommendation == "rethink":
            insights.append(
                "Agent should re-approach this task with a different strategy."
            )
        elif recommendation == "retry":
            insights.append("Transient issue — retry with the same approach.")

        return insights

    def _compute_retry_delay(self, attempt: int) -> float:
        """Exponential back-off capped at max_retry_delay."""
        delay = self._base_retry_delay * (2 ** (attempt - 1))
        return min(delay, self._max_retry_delay)
