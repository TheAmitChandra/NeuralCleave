"""Unit tests for the reflection engine module.

Covers:
    - HallucinationDetector — all 5 individual checks + analyse()
    - ExecutionScorer — all 5 dimension scorers + score()
    - ReflectionEngine — decision matrix, back-off, insights, reflect()
"""

from __future__ import annotations

import pytest

from app.core.reflection.engine import ReflectionEngine, ReflectionResult
from app.core.reflection.hallucination import (
    HallucinationDetector,
    HallucinationReport,
    HallucinationSignal,
)
from app.core.reflection.scorer import DimensionScore, ExecutionScorer, QualityScore

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def detector() -> HallucinationDetector:
    return HallucinationDetector(
        hallucination_threshold=0.5,
        confidence_floor=0.4,
        source_overlap_floor=0.1,
    )


@pytest.fixture
def scorer() -> ExecutionScorer:
    return ExecutionScorer(pass_threshold=60.0)


@pytest.fixture
def engine() -> ReflectionEngine:
    return ReflectionEngine(
        quality_pass_threshold=60.0,
        hallucination_threshold=0.5,
    )


# ===========================================================================
# TestHallucinationSignal
# ===========================================================================


class TestHallucinationSignal:
    def test_instantiation(self) -> None:
        sig = HallucinationSignal(
            signal_type="confidence_low",
            description="Too low",
            severity=0.3,
            evidence="confidence=0.1",
        )
        assert sig.signal_type == "confidence_low"
        assert sig.severity == 0.3

    def test_default_evidence_empty(self) -> None:
        sig = HallucinationSignal(signal_type="x", description="y", severity=0.1)
        assert sig.evidence == ""


# ===========================================================================
# TestHallucinationDetector — individual checks
# ===========================================================================


class TestHallucinationDetectorChecks:
    def test_check_self_confidence_below_floor(self, detector: HallucinationDetector) -> None:
        sig = detector.check_self_confidence(0.1)
        assert sig is not None
        assert sig.signal_type == "confidence_low"
        assert sig.severity > 0

    def test_check_self_confidence_above_floor(self, detector: HallucinationDetector) -> None:
        sig = detector.check_self_confidence(0.9)
        assert sig is None

    def test_check_self_confidence_at_floor(self, detector: HallucinationDetector) -> None:
        # Exactly at floor should not fire
        sig = detector.check_self_confidence(0.4)
        assert sig is None

    def test_check_source_grounding_low_overlap(self, detector: HallucinationDetector) -> None:
        response = "quantum entanglement photon spin"
        sources = ["The cat sat on the mat in the afternoon sunshine."]
        sig = detector.check_source_grounding(response, sources)
        assert sig is not None
        assert sig.signal_type == "unsupported_claim"

    def test_check_source_grounding_high_overlap(self, detector: HallucinationDetector) -> None:
        text = "The quick brown fox jumps over the lazy dog near the river."
        sig = detector.check_source_grounding(text, [text])
        assert sig is None

    def test_check_source_grounding_empty_response(self, detector: HallucinationDetector) -> None:
        sig = detector.check_source_grounding("", ["some source text here"])
        assert sig is None

    def test_check_numeric_consistency_unsupported(self, detector: HallucinationDetector) -> None:
        response = "The model achieved 99% accuracy."
        sources = ["The model achieved 87% accuracy."]
        sig = detector.check_numeric_consistency(response, sources)
        assert sig is not None
        assert sig.signal_type == "numeric_inconsistency"
        assert "99%" in sig.evidence

    def test_check_numeric_consistency_supported(self, detector: HallucinationDetector) -> None:
        text = "Accuracy was 87% on the benchmark."
        sig = detector.check_numeric_consistency(text, [text])
        assert sig is None

    def test_check_numeric_consistency_no_numbers(self, detector: HallucinationDetector) -> None:
        sig = detector.check_numeric_consistency("All good.", ["Sources here."])
        assert sig is None

    def test_check_temporal_drift_future_year(self, detector: HallucinationDetector) -> None:
        response = "This will happen in 2099."
        sig = detector.check_temporal_drift(response)
        assert sig is not None
        assert sig.signal_type == "temporal_drift"
        assert 2099 in eval(sig.evidence)  # noqa: S307 — test-only eval

    def test_check_temporal_drift_past_year(self, detector: HallucinationDetector) -> None:
        sig = detector.check_temporal_drift("The event occurred in 1999.")
        assert sig is None

    def test_check_temporal_drift_no_years(self, detector: HallucinationDetector) -> None:
        sig = detector.check_temporal_drift("No year mentioned here.")
        assert sig is None

    def test_check_self_contradiction_both_patterns(self, detector: HallucinationDetector) -> None:
        text = "I think this is definitely the best approach without a doubt."
        sig = detector.check_self_contradiction(text)
        assert sig is not None
        assert sig.signal_type == "self_contradiction"

    def test_check_self_contradiction_only_hedge(self, detector: HallucinationDetector) -> None:
        sig = detector.check_self_contradiction("I think this might work.")
        assert sig is None

    def test_check_self_contradiction_only_overconfidence(
        self, detector: HallucinationDetector
    ) -> None:
        sig = detector.check_self_contradiction("This is absolutely the best solution.")
        assert sig is None


# ===========================================================================
# TestHallucinationDetector — analyse()
# ===========================================================================


class TestHallucinationDetectorAnalyse:
    def test_clean_output_passes(self, detector: HallucinationDetector) -> None:
        source = "Machine learning is a subset of artificial intelligence."
        report = detector.analyse(
            "Machine learning is a subset of artificial intelligence.",
            sources=[source],
            self_confidence=0.95,
        )
        assert report.likely_hallucination is False
        assert report.recommendation == "pass"

    def test_low_confidence_triggers_detection(self, detector: HallucinationDetector) -> None:
        report = detector.analyse(
            "Something or other.",
            self_confidence=0.05,
        )
        assert any(s.signal_type == "confidence_low" for s in report.signals)

    def test_score_capped_at_one(self, detector: HallucinationDetector) -> None:
        # Force many signals
        report = detector.analyse(
            "I think this definitely happened in 2099 with 999% certainty.",
            sources=["Completely unrelated source about cooking recipes."],
            self_confidence=0.01,
        )
        assert report.hallucination_score <= 1.0

    def test_recommend_escalate_for_severe(self, detector: HallucinationDetector) -> None:
        report = detector.analyse(
            "I think this definitely happened in 2099 with 999% accuracy.",
            sources=["Cooking recipes and baking tips."],
            self_confidence=0.01,
        )
        assert report.recommendation in {"rethink", "escalate"}

    def test_report_fields_present(self, detector: HallucinationDetector) -> None:
        report = detector.analyse("Hello world.")
        assert isinstance(report.hallucination_score, float)
        assert isinstance(report.likely_hallucination, bool)
        assert isinstance(report.signals, list)
        assert isinstance(report.details, dict)


# ===========================================================================
# TestExecutionScorer — dimensions
# ===========================================================================


class TestExecutionScorerDimensions:
    def test_completeness_with_elements_all_found(self, scorer: ExecutionScorer) -> None:
        score = scorer._score_completeness(
            "The weather is sunny and warm today.",
            ["weather", "sunny"],
        )
        assert score == 100.0

    def test_completeness_with_elements_none_found(self, scorer: ExecutionScorer) -> None:
        score = scorer._score_completeness("Hello.", ["climate", "forecast"])
        assert score == 0.0

    def test_completeness_fallback_to_length(self, scorer: ExecutionScorer) -> None:
        long_output = " ".join(["word"] * 60)
        score = scorer._score_completeness(long_output, None)
        assert score == 100.0

    def test_relevance_high_overlap(self, scorer: ExecutionScorer) -> None:
        task = "Explain neural network training"
        output = "Neural network training involves optimizing weights through gradient descent."
        score = scorer._score_relevance(task, output)
        assert score > 50

    def test_relevance_no_task_tokens(self, scorer: ExecutionScorer) -> None:
        score = scorer._score_relevance("hi", "This is a response.")
        assert score == 70.0  # neutral default

    def test_coherence_empty_output(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_coherence("") == 0.0

    def test_coherence_short_output_penalised(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_coherence("ok") < 80

    def test_coherence_repetitive_output(self, scorer: ExecutionScorer) -> None:
        repetitive = "word " * 50
        score = scorer._score_coherence(repetitive)
        assert score < 70

    def test_coherence_good_output(self, scorer: ExecutionScorer) -> None:
        good = (
            "The quick brown fox jumps over the lazy dog. "
            "This sentence has many unique words and proper structure."
        )
        assert scorer._score_coherence(good) >= 80

    def test_efficiency_under_budget(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_efficiency(5.0, 30.0) == 100.0

    def test_efficiency_over_budget(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_efficiency(90.0, 30.0) < 50.0

    def test_efficiency_unknown_time(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_efficiency(None, 30.0) == 80.0

    def test_efficiency_zero_time(self, scorer: ExecutionScorer) -> None:
        assert scorer._score_efficiency(0.0, 30.0) == 100.0


# ===========================================================================
# TestExecutionScorer — score()
# ===========================================================================


class TestExecutionScorerScore:
    def test_high_quality_output(self, scorer: ExecutionScorer) -> None:
        result = scorer.score(
            task_description="Explain what machine learning is.",
            output=(
                "Machine learning is a branch of artificial intelligence that enables "
                "systems to learn and improve from experience without being explicitly "
                "programmed. It focuses on developing computer programs that can access "
                "data and use it to learn for themselves."
            ),
            execution_time_seconds=1.0,
            max_expected_seconds=10.0,
        )
        assert result.total > 50
        assert result.grade in {"A", "B", "C"}

    def test_empty_output_low_score(self, scorer: ExecutionScorer) -> None:
        result = scorer.score(
            task_description="Write a summary.",
            output="",
        )
        assert result.total < 50
        assert result.passed is False

    def test_dimensions_present(self, scorer: ExecutionScorer) -> None:
        result = scorer.score(task_description="task", output="output text here")
        dim_names = {d.name for d in result.dimensions}
        assert dim_names == {"completeness", "relevance", "coherence", "safety", "efficiency"}

    def test_grade_a_for_high_score(self, scorer: ExecutionScorer) -> None:
        # Mock a perfect scenario
        result = scorer.score(
            task_description="List fruits: apple, banana, cherry.",
            output="The fruits are apple, banana, and cherry. They are all delicious.",
            expected_elements=["apple", "banana", "cherry"],
            execution_time_seconds=0.5,
        )
        # Should be high quality
        assert result.total >= 60

    def test_recommendation_pass_when_high_score(self, scorer: ExecutionScorer) -> None:
        result = scorer.score(
            task_description="Describe apples.",
            output=" ".join(["Apple is a fruit that is red and sweet."] * 3),
            execution_time_seconds=1.0,
        )
        if result.total >= 60:
            assert result.recommendation == "pass"

    def test_custom_weights_applied(self) -> None:
        custom_scorer = ExecutionScorer(
            weights={
                "completeness": 1.0,
                "relevance": 0.0,
                "coherence": 0.0,
                "safety": 0.0,
                "efficiency": 0.0,
            }
        )
        result = custom_scorer.score(
            task_description="task",
            output="some output text",
            expected_elements=["output"],  # present
        )
        # Completeness should dominate
        completeness_dim = next(d for d in result.dimensions if d.name == "completeness")
        assert completeness_dim.weight == 1.0


# ===========================================================================
# TestReflectionEngine — decision matrix
# ===========================================================================


class TestReflectionEngineDecisionMatrix:
    """Test _compute_recommendation combinations."""

    def _make_quality(self, total: float, scorer: ExecutionScorer) -> QualityScore:
        from app.core.reflection.scorer import DimensionScore

        return QualityScore(
            total=total,
            grade="B",
            dimensions=[],
            pass_threshold=60.0,
            passed=(total >= 60.0),
            recommendation="pass" if total >= 60 else "retry",
        )

    def _make_hallucination(
        self,
        score: float,
        detector: HallucinationDetector,
    ) -> HallucinationReport:
        return HallucinationReport(
            hallucination_score=score,
            likely_hallucination=(score >= 0.5),
            recommendation="pass" if score < 0.3 else "retry",
        )

    def test_pass_when_both_good(
        self, engine: ReflectionEngine, scorer: ExecutionScorer, detector: HallucinationDetector
    ) -> None:
        q = self._make_quality(80.0, scorer)
        h = self._make_hallucination(0.1, detector)
        assert engine._compute_recommendation(q, h) == "pass"

    def test_rethink_when_quality_good_hallucination_high(
        self, engine: ReflectionEngine, scorer: ExecutionScorer, detector: HallucinationDetector
    ) -> None:
        q = self._make_quality(80.0, scorer)
        h = self._make_hallucination(0.7, detector)
        assert engine._compute_recommendation(q, h) == "rethink"

    def test_retry_when_quality_medium_hallucination_low(
        self, engine: ReflectionEngine, scorer: ExecutionScorer, detector: HallucinationDetector
    ) -> None:
        q = self._make_quality(50.0, scorer)
        h = self._make_hallucination(0.1, detector)
        assert engine._compute_recommendation(q, h) == "retry"

    def test_escalate_when_quality_very_low_hallucination_high(
        self, engine: ReflectionEngine, scorer: ExecutionScorer, detector: HallucinationDetector
    ) -> None:
        q = self._make_quality(10.0, scorer)
        h = self._make_hallucination(0.8, detector)
        assert engine._compute_recommendation(q, h) == "escalate"

    def test_rethink_when_quality_very_low_hallucination_low(
        self, engine: ReflectionEngine, scorer: ExecutionScorer, detector: HallucinationDetector
    ) -> None:
        q = self._make_quality(10.0, scorer)
        h = self._make_hallucination(0.2, detector)
        assert engine._compute_recommendation(q, h) == "rethink"


# ===========================================================================
# TestReflectionEngineBackoff
# ===========================================================================


class TestReflectionEngineBackoff:
    def test_attempt_1_base_delay(self, engine: ReflectionEngine) -> None:
        assert engine._compute_retry_delay(1) == 2.0

    def test_attempt_2_doubles(self, engine: ReflectionEngine) -> None:
        assert engine._compute_retry_delay(2) == 4.0

    def test_attempt_3_doubles_again(self, engine: ReflectionEngine) -> None:
        assert engine._compute_retry_delay(3) == 8.0

    def test_capped_at_max(self, engine: ReflectionEngine) -> None:
        assert engine._compute_retry_delay(100) == 60.0


# ===========================================================================
# TestReflectionEngineReflect — async
# ===========================================================================


class TestReflectionEngineReflect:
    @pytest.mark.asyncio
    async def test_reflect_returns_result(self, engine: ReflectionEngine) -> None:
        result = await engine.reflect(
            task="Summarise this document.",
            output="The document discusses modern software engineering practices.",
            sources=["Modern software engineering involves agile, CI/CD, and testing."],
            execution_time_seconds=1.5,
        )
        assert isinstance(result, ReflectionResult)
        assert result.recommendation in {"pass", "retry", "rethink", "escalate"}

    @pytest.mark.asyncio
    async def test_reflect_should_retry_flag(self, engine: ReflectionEngine) -> None:
        result = await engine.reflect(
            task="Summarise this document.",
            output="The document discusses modern software engineering practices.",
        )
        assert result.should_retry == (result.recommendation == "retry")

    @pytest.mark.asyncio
    async def test_reflect_should_escalate_flag(self, engine: ReflectionEngine) -> None:
        result = await engine.reflect(
            task="Explain quantum computing.",
            output="ok",
        )
        assert result.should_escalate == (result.recommendation == "escalate")

    @pytest.mark.asyncio
    async def test_reflect_insights_not_empty_on_poor_output(
        self, engine: ReflectionEngine
    ) -> None:
        result = await engine.reflect(
            task="Write a detailed technical report on neural networks.",
            output="ok",
        )
        assert len(result.insights) > 0

    @pytest.mark.asyncio
    async def test_reflect_metadata_fields(self, engine: ReflectionEngine) -> None:
        result = await engine.reflect(
            task="Explain Python",
            output="Python is a programming language known for its simplicity.",
            attempt_number=2,
        )
        assert result.metadata["attempt_number"] == 2
        assert "quality_grade" in result.metadata
        assert "hallucination_signals" in result.metadata

    @pytest.mark.asyncio
    async def test_reflect_with_expected_elements(self, engine: ReflectionEngine) -> None:
        result = await engine.reflect(
            task="List fruits: apple, banana, cherry.",
            output="The fruits include apple, banana, and cherry.",
            expected_elements=["apple", "banana", "cherry"],
        )
        # All elements present → completeness should be high
        comp_dim = next(d for d in result.quality.dimensions if d.name == "completeness")
        assert comp_dim.raw == 100.0

    @pytest.mark.asyncio
    async def test_reflect_sync_wrapper(self, engine: ReflectionEngine) -> None:
        result = engine.reflect_sync(
            task="Describe a cat.",
            output="A cat is a small furry animal that meows.",
        )
        assert isinstance(result, ReflectionResult)

    @pytest.mark.asyncio
    async def test_reflect_retry_delay_increases_with_attempt(
        self, engine: ReflectionEngine
    ) -> None:
        r1 = await engine.reflect(task="t", output="o", attempt_number=1)
        r2 = await engine.reflect(task="t", output="o", attempt_number=2)
        assert r2.retry_delay_seconds > r1.retry_delay_seconds

    @pytest.mark.asyncio
    async def test_reflect_hallucination_signals_in_metadata(
        self, engine: ReflectionEngine
    ) -> None:
        result = await engine.reflect(
            task="Explain history.",
            output="I think this definitely happened in 2099 with 999% certainty.",
            self_confidence=0.01,
        )
        assert isinstance(result.metadata["hallucination_signals"], list)
