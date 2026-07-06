"""Unit tests for cortexflow.reflection.engine."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cortexflow_ai.models.router import GenerationResult
from cortexflow_ai.reflection.engine import (
    ReflectionEngine,
    ReflectionResult,
    _parse_score,
)

# ---------------------------------------------------------------------------
# _parse_score
# ---------------------------------------------------------------------------


def test_parse_score_valid_json() -> None:
    score, reason = _parse_score('{"score": 85, "reason": "clear and concise"}')
    assert score == 85.0
    assert reason == "clear and concise"


def test_parse_score_with_code_fence() -> None:
    score, reason = _parse_score('```json\n{"score": 72, "reason": "ok"}\n```')
    assert score == 72.0


def test_parse_score_clamps_above_100() -> None:
    score, _ = _parse_score('{"score": 999, "reason": ""}')
    assert score == 100.0


def test_parse_score_clamps_below_0() -> None:
    score, _ = _parse_score('{"score": -5, "reason": ""}')
    assert score == 0.0


def test_parse_score_falls_back_to_number_in_text() -> None:
    score, _ = _parse_score("The response quality is 68 out of 100.")
    assert score == 68.0


def test_parse_score_returns_default_on_garbage() -> None:
    score, _ = _parse_score("no numbers here at all!")
    assert score == 80.0


# ---------------------------------------------------------------------------
# ReflectionEngine — disabled mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_disabled_skips_scoring() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), enabled=False)
    result = await engine.reflect("What is 2+2?", "It is 4.")
    assert result.score == 100.0
    assert result.final_response == "It is 4."
    assert result.corrected is False
    assert result.correction_attempts == 0


# ---------------------------------------------------------------------------
# ReflectionEngine — enabled with mocked router
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reflect_high_score_no_correction() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0)
    high_score_response = GenerationResult(
        text='{"score": 90, "reason": "excellent"}',
        model="gemini-flash",
        provider="google",
    )

    with patch.object(engine._router, "generate", new=AsyncMock(return_value=high_score_response)):
        result = await engine.reflect("What is Python?", "Python is a programming language.")

    assert result.score == 90.0
    assert result.corrected is False
    assert result.final_response == "Python is a programming language."


@pytest.mark.asyncio
async def test_reflect_low_score_triggers_correction() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0, max_corrections=1)

    low_score = GenerationResult(text='{"score": 40, "reason": "incomplete"}', model="m", provider="p")
    high_score = GenerationResult(text='{"score": 85, "reason": "better"}', model="m", provider="p")
    corrected_response = GenerationResult(text="Here is a better answer.", model="m", provider="p")

    call_count = 0

    async def mock_generate(prompt: str, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return low_score          # first score
        if call_count == 2:
            return corrected_response  # correction attempt
        return high_score             # second score

    with patch.object(engine._router, "generate", new=AsyncMock(side_effect=mock_generate)):
        result = await engine.reflect("Explain quantum computing", "Quantum is hard.")

    assert result.corrected is True
    assert result.correction_attempts == 1
    assert result.final_response == "Here is a better answer."


@pytest.mark.asyncio
async def test_reflect_correction_not_accepted_if_score_worse() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0, max_corrections=1)

    low_score = GenerationResult(text='{"score": 50, "reason": "bad"}', model="m", provider="p")
    worse_score = GenerationResult(text='{"score": 30, "reason": "worse"}', model="m", provider="p")
    corrected = GenerationResult(text="Corrected text.", model="m", provider="p")

    call_count = 0

    async def mock_generate(prompt: str, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return low_score
        if call_count == 2:
            return corrected
        return worse_score  # re-score is worse

    with patch.object(engine._router, "generate", new=AsyncMock(side_effect=mock_generate)):
        result = await engine.reflect("Hello", "Original answer.")

    # Correction was attempted but rejected because it made things worse
    assert result.final_response == "Original answer."


@pytest.mark.asyncio
async def test_correct_failure_returns_original_response() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0, max_corrections=1)

    low_score = GenerationResult(text='{"score": 40, "reason": "incomplete"}', model="m", provider="p")
    same_score = GenerationResult(text='{"score": 40, "reason": "still incomplete"}', model="m", provider="p")

    call_count = 0

    async def mock_generate(prompt: str, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return low_score        # first score
        if call_count == 2:
            raise RuntimeError("model unavailable during correction")
        return same_score           # re-score of the (unchanged) original

    with patch.object(engine._router, "generate", new=AsyncMock(side_effect=mock_generate)):
        result = await engine.reflect("Explain X", "Original answer.")

    # _correct() swallowed the exception and returned the original text unchanged
    assert result.final_response == "Original answer."
    assert result.correction_attempts == 1
    assert result.corrected is False  # text never actually changed


@pytest.mark.asyncio
async def test_reflect_scoring_failure_uses_default_score() -> None:
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0)

    with patch.object(
        engine._router, "generate", new=AsyncMock(side_effect=RuntimeError("all providers down"))
    ):
        result = await engine.reflect("test", "answer")

    assert result.score == 80.0  # default fallback
    assert result.corrected is False


# ---------------------------------------------------------------------------
# _correct includes original response in the prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correct_includes_original_response_in_prompt() -> None:
    """_correct() must pass the original response text to the correction prompt.

    Before the fix, _CORRECTION_PROMPT had no {response} slot, so the LLM
    was asked to self-correct without seeing what it originally wrote.
    """
    from cortexflow_ai.models.router import ModelRouter

    engine = ReflectionEngine(ModelRouter(), quality_threshold=70.0, max_corrections=1)

    low_score = GenerationResult(text='{"score": 40, "reason": "too vague"}', model="m", provider="p")
    high_score = GenerationResult(text='{"score": 85, "reason": "better"}', model="m", provider="p")
    corrected = GenerationResult(text="Improved answer here.", model="m", provider="p")

    captured_prompts: list[str] = []

    async def mock_generate(prompt: str, **kwargs):
        captured_prompts.append(prompt)
        if len(captured_prompts) == 1:
            return low_score
        if len(captured_prompts) == 2:
            return corrected
        return high_score

    original_response = "This is the original response text."
    with patch.object(engine._router, "generate", new=AsyncMock(side_effect=mock_generate)):
        result = await engine.reflect("Explain Python", original_response)

    # The second call is _correct() — it must contain the original response
    correction_prompt = captured_prompts[1]
    assert original_response in correction_prompt, (
        f"Original response not found in correction prompt.\n"
        f"Prompt was:\n{correction_prompt}"
    )
    assert result.final_response == "Improved answer here."


# ---------------------------------------------------------------------------
# ReflectionResult
# ---------------------------------------------------------------------------


def test_reflection_result_defaults() -> None:
    r = ReflectionResult(
        original_response="orig",
        final_response="final",
        score=75.0,
        reason="ok",
    )
    assert r.corrected is False
    assert r.correction_attempts == 0
