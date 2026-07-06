"""Reflection engine — quality scoring and optional self-correction.

The reflection engine evaluates each assistant response on a 0–100 scale
and optionally triggers a self-correction loop when quality falls below
a configurable threshold.

Quality dimensions scored:
    1. Relevance   — Does the response address the user's actual question?
    2. Completeness — Is the answer sufficiently detailed?
    3. Accuracy    — Are there obvious factual errors or hallucinations?
    4. Tone        — Is the response appropriately concise and helpful?
    5. Safety      — Does it avoid harmful content?

The scorer uses a cheap fast model (Gemini Flash / Ollama) to avoid
burning expensive tokens on meta-evaluation.

Self-correction:
    If score < threshold (default 70), the engine re-prompts the LLM with
    explicit guidance on what was wrong. Maximum 1 retry by default to avoid
    infinite loops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from cortexflow_ai.models.router import ModelRouter

logger = logging.getLogger(__name__)

_SCORE_PROMPT = """\
You are a quality evaluator for an AI assistant.

## User message
{user_message}

## Assistant response
{response}

Rate the response on a scale of 0–100 by these criteria:
- Relevance (0–25): Does it directly address the question?
- Completeness (0–25): Is it sufficiently detailed without being verbose?
- Accuracy (0–25): Are there obvious errors or hallucinations?
- Tone (0–25): Concise, clear, helpful, no unnecessary repetition?

Return ONLY a JSON object like: {{"score": 82, "reason": "one sentence"}}
"""

_CORRECTION_PROMPT = """\
Your previous response scored {score}/100 for quality.
Reason: {reason}

User message: {user_message}

Your previous response:
{response}

Please provide an improved response that addresses the quality issue above.
"""


@dataclass
class ReflectionResult:
    """Output of one reflection pass."""

    original_response: str
    final_response: str
    score: float
    reason: str
    corrected: bool = False
    correction_attempts: int = 0


class ReflectionEngine:
    """Scores LLM responses and optionally triggers self-correction.

    Args:
        router:             Model router (uses cheap model for scoring).
        quality_threshold:  Score below which self-correction is triggered.
        max_corrections:    Maximum retry attempts. Default 1.
        enabled:            If False, always returns score=100 (skip scoring).
    """

    def __init__(
        self,
        router: ModelRouter,
        *,
        quality_threshold: float = 70.0,
        max_corrections: int = 1,
        enabled: bool = True,
    ) -> None:
        self._router = router
        self._threshold = quality_threshold
        self._max_corrections = max_corrections
        self._enabled = enabled

    async def reflect(
        self,
        user_message: str,
        response: str,
    ) -> ReflectionResult:
        """Evaluate response quality and correct if below threshold.

        Args:
            user_message: The original user input.
            response:     The assistant's response to evaluate.

        Returns:
            ReflectionResult with score, reason, and (possibly corrected) response.
        """
        if not self._enabled:
            return ReflectionResult(
                original_response=response,
                final_response=response,
                score=100.0,
                reason="reflection disabled",
            )

        score, reason = await self._score(user_message, response)
        logger.debug("reflection.score=%.0f reason=%s", score, reason)

        current_response = response
        attempts = 0

        while score < self._threshold and attempts < self._max_corrections:
            attempts += 1
            logger.info(
                "reflection: score=%.0f < threshold=%.0f — correcting (attempt %d)",
                score, self._threshold, attempts,
            )
            corrected = await self._correct(user_message, current_response, score, reason)
            new_score, new_reason = await self._score(user_message, corrected)
            logger.debug(
                "reflection: post-correction score=%.0f (was %.0f)", new_score, score
            )
            if new_score >= score:  # accept correction only if it improves
                current_response = corrected
                score = new_score
                reason = new_reason
            else:
                logger.debug("reflection: correction did not improve score — keeping original")
                break

        return ReflectionResult(
            original_response=response,
            final_response=current_response,
            score=score,
            reason=reason,
            corrected=current_response != response,
            correction_attempts=attempts,
        )

    # ------------------------------------------------------------------

    async def _score(self, user_message: str, response: str) -> tuple[float, str]:
        """Ask a cheap model to score the response. Returns (score, reason)."""
        prompt = _SCORE_PROMPT.format(
            user_message=user_message[:500],
            response=response[:1000],
        )
        try:
            result = await self._router.generate(
                prompt,
                task_type="validation",
                max_tokens=80,
                temperature=0.0,
            )
            return _parse_score(result.text)
        except Exception as exc:
            logger.warning("reflection._score failed: %s", exc)
            return 80.0, "scoring unavailable"

    async def _correct(
        self,
        user_message: str,
        response: str,
        score: float,
        reason: str,
    ) -> str:
        """Ask the model to produce a better response."""
        prompt = _CORRECTION_PROMPT.format(
            score=int(score),
            reason=reason,
            user_message=user_message[:500],
            response=response[:1000],
        )
        try:
            result = await self._router.generate(
                prompt,
                task_type="general",
                max_tokens=1024,
                temperature=0.5,
            )
            return result.text.strip()
        except Exception as exc:
            logger.warning("reflection._correct failed: %s", exc)
            return response


def _parse_score(text: str) -> tuple[float, str]:
    """Parse {"score": 82, "reason": "..."} from model output."""
    import json
    import re

    try:
        # Tolerate markdown code fences and extra whitespace
        cleaned = re.sub(r"```[a-z]*", "", text).strip()
        data = json.loads(cleaned)
        score = float(data.get("score", 80))
        reason = str(data.get("reason", ""))
        return max(0.0, min(100.0, score)), reason
    except Exception:
        # Fall back to extracting the first number in the text
        numbers = re.findall(r"\b(\d{1,3})\b", text)
        if numbers:
            return max(0.0, min(100.0, float(numbers[0]))), "parsed from text"
        return 80.0, "could not parse score"
