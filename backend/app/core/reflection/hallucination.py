"""Hallucination Detection — confidence thresholding and fact-grounding checks.

Hallucination signals this module detects:
    1. Low LLM self-reported confidence (if structured output includes a score)
    2. Unsupported factual claims — claims not traceable to a provided source
    3. Numeric inconsistency — numbers in the response that contradict sources
    4. Temporal drift — dates/years that are logically impossible
    5. Contradiction detection — response contradicts itself

Architecture:
    ``HallucinationSignal``  — individual detection result
    ``HallucinationReport``  — aggregate over all signals
    ``HallucinationDetector`` — stateless detector, all checks exposed individually

Usage::

    detector = HallucinationDetector()
    report = detector.analyse(
        response="The model achieved 99% accuracy on MNIST.",
        sources=["The model achieved 87% accuracy."],
        self_confidence=0.4,
    )
    if report.likely_hallucination:
        # re-trigger or escalate
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HallucinationSignal:
    """A single detected hallucination signal."""

    signal_type: str        # confidence_low | unsupported_claim | numeric_inconsistency | temporal_drift | self_contradiction
    description: str
    severity: float         # 0.0–1.0 contribution to final score
    evidence: str = ""


@dataclass
class HallucinationReport:
    """Aggregate result of hallucination analysis.

    Attributes:
        hallucination_score:  0.0 (clean) – 1.0 (definite hallucination).
        likely_hallucination: True when score ≥ threshold (default 0.5).
        signals:              Individual signals that fired.
        recommendation:       ``"pass" | "retry" | "rethink" | "escalate"``.
        details:              Diagnostic payload.
    """

    hallucination_score: float
    likely_hallucination: bool
    signals: list[HallucinationSignal] = field(default_factory=list)
    recommendation: str = "pass"
    details: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Pattern helpers
# ---------------------------------------------------------------------------

# Matches years — used for temporal drift checks
_YEAR_PATTERN = re.compile(r"\b(1[89]\d{2}|20\d{2})\b")

# Matches floating-point / integer numbers in text
_NUMBER_PATTERN = re.compile(r"\b\d+(?:\.\d+)?%?")

# Phrases that suggest high uncertainty (hedging language → may indicate fabrication)
_HEDGE_PHRASES = re.compile(
    r"\b(I (think|believe|guess|assume)|probably|possibly|might be|could be|"
    r"not (sure|certain)|may be|perhaps|approximately|around|roughly)\b",
    re.IGNORECASE,
)

# Absolute-certainty phrases used when evidence is absent (overconfidence signal)
_OVERCONFIDENCE_PHRASES = re.compile(
    r"\b(definitely|absolutely|certainly|undoubtedly|without (a )?doubt|"
    r"100%|always|never|every single|all \w+ do)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class HallucinationDetector:
    """Stateless hallucination detector.

    Parameters:
        hallucination_threshold: Score ≥ this → ``likely_hallucination=True``.
        confidence_floor:        Self-reported confidence below this is flagged.
        source_overlap_floor:    Minimum token-overlap ratio with sources before
                                 flagging an unsupported claim.
    """

    def __init__(
        self,
        hallucination_threshold: float = 0.5,
        confidence_floor: float = 0.4,
        source_overlap_floor: float = 0.1,
    ) -> None:
        self._threshold = hallucination_threshold
        self._confidence_floor = confidence_floor
        self._source_overlap_floor = source_overlap_floor

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyse(
        self,
        response: str,
        *,
        sources: list[str] | None = None,
        self_confidence: float | None = None,
    ) -> HallucinationReport:
        """Run all hallucination checks on ``response``.

        Parameters:
            response:         The LLM-generated text to examine.
            sources:          Reference texts the response should be grounded in.
            self_confidence:  Optional 0–1 score from the model's own output.

        Returns:
            ``HallucinationReport``.
        """
        signals: list[HallucinationSignal] = []

        if self_confidence is not None:
            sig = self.check_self_confidence(self_confidence)
            if sig:
                signals.append(sig)

        if sources:
            sig = self.check_source_grounding(response, sources)
            if sig:
                signals.append(sig)

            sig = self.check_numeric_consistency(response, sources)
            if sig:
                signals.append(sig)

        sig = self.check_temporal_drift(response)
        if sig:
            signals.append(sig)

        sig = self.check_self_contradiction(response)
        if sig:
            signals.append(sig)

        score = float(min(sum(s.severity for s in signals), 1.0))
        likely = score >= self._threshold
        recommendation = self._recommend(score)

        if likely:
            logger.warning(
                "hallucination.detected",
                score=round(score, 3),
                signals=[s.signal_type for s in signals],
                recommendation=recommendation,
            )

        return HallucinationReport(
            hallucination_score=round(score, 3),
            likely_hallucination=likely,
            signals=signals,
            recommendation=recommendation,
            details={
                "signal_count": len(signals),
                "response_length": len(response),
                "source_count": len(sources) if sources else 0,
            },
        )

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    def check_self_confidence(self, confidence: float) -> HallucinationSignal | None:
        """Flag if model self-reported confidence is below threshold."""
        if confidence < self._confidence_floor:
            severity = (self._confidence_floor - confidence) / self._confidence_floor * 0.4
            return HallucinationSignal(
                signal_type="confidence_low",
                description=f"Self-reported confidence {confidence:.2f} below floor {self._confidence_floor:.2f}",
                severity=round(severity, 3),
                evidence=f"confidence={confidence}",
            )
        return None

    def check_source_grounding(
        self, response: str, sources: list[str]
    ) -> HallucinationSignal | None:
        """Check token-level overlap between response and source material."""
        resp_tokens = set(re.findall(r"\b\w{4,}\b", response.lower()))
        source_tokens = set()
        for src in sources:
            source_tokens.update(re.findall(r"\b\w{4,}\b", src.lower()))

        if not resp_tokens:
            return None

        overlap = len(resp_tokens & source_tokens) / len(resp_tokens)
        if overlap < self._source_overlap_floor:
            severity = (self._source_overlap_floor - overlap) / self._source_overlap_floor * 0.45
            return HallucinationSignal(
                signal_type="unsupported_claim",
                description=f"Low token overlap with sources ({overlap:.2%})",
                severity=round(severity, 3),
                evidence=f"overlap_ratio={overlap:.3f}",
            )
        return None

    def check_numeric_consistency(
        self, response: str, sources: list[str]
    ) -> HallucinationSignal | None:
        """Flag numbers in the response that don't appear in any source."""
        resp_numbers = set(_NUMBER_PATTERN.findall(response))
        if not resp_numbers:
            return None

        source_text = " ".join(sources)
        source_numbers = set(_NUMBER_PATTERN.findall(source_text))

        unsupported = resp_numbers - source_numbers
        if unsupported:
            severity = min(len(unsupported) * 0.15, 0.4)
            return HallucinationSignal(
                signal_type="numeric_inconsistency",
                description=f"Numbers in response not found in sources: {unsupported}",
                severity=round(severity, 3),
                evidence=str(unsupported),
            )
        return None

    def check_temporal_drift(self, response: str) -> HallucinationSignal | None:
        """Flag years that are logically impossible (e.g., future years > current year)."""
        years = [int(y) for y in _YEAR_PATTERN.findall(response)]
        # Current year hardcoded conservatively; adjust via config if needed
        current_year = 2026
        impossible = [y for y in years if y > current_year]
        if impossible:
            return HallucinationSignal(
                signal_type="temporal_drift",
                description=f"Future years referenced: {impossible}",
                severity=0.3,
                evidence=str(impossible),
            )
        return None

    def check_self_contradiction(self, response: str) -> HallucinationSignal | None:
        """Detect simple self-contradictions using hedge + overconfidence co-occurrence."""
        has_hedge = bool(_HEDGE_PHRASES.search(response))
        has_overconfidence = bool(_OVERCONFIDENCE_PHRASES.search(response))
        if has_hedge and has_overconfidence:
            return HallucinationSignal(
                signal_type="self_contradiction",
                description="Response mixes hedging and overconfidence language",
                severity=0.2,
                evidence="hedge+overconfidence co-occurrence",
            )
        return None

    # ------------------------------------------------------------------
    # Recommendation engine
    # ------------------------------------------------------------------

    def _recommend(self, score: float) -> str:
        if score < 0.3:
            return "pass"
        if score < 0.55:
            return "retry"
        if score < 0.8:
            return "rethink"
        return "escalate"
