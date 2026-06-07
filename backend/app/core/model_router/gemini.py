"""Gemini API client — primary LLM provider."""

import structlog
from google import generativeai as genai
from google.generativeai.types import GenerateContentResponse

from app.config import get_settings
from app.core.observability.metrics import (
    llm_cost_usd_total,
    llm_request_duration_seconds,
    llm_tokens_used_total,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

# Cost per 1k tokens (USD) — approximate, update as pricing changes
_COST_PER_1K: dict[str, dict[str, float]] = {
    "gemini-1.5-pro": {"input": 0.00125, "output": 0.005},
    "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
    "gemini-2.0-flash": {"input": 0.0001, "output": 0.0004},
}

_DEFAULT_MODEL = "gemini-2.0-flash"


class GeminiClient:
    """Thin async wrapper around the Gemini generative AI SDK."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        key = api_key or settings.GEMINI_API_KEY
        if not key:
            raise ValueError("GEMINI_API_KEY is not configured")
        genai.configure(api_key=key)
        self.model_name = model
        self._model = genai.GenerativeModel(model)

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        task_type: str = "general",
    ) -> str:
        """Generate text from a prompt. Returns the response text."""
        import time

        if system_instruction:
            model = genai.GenerativeModel(self.model_name, system_instruction=system_instruction)
        else:
            model = self._model

        start = time.perf_counter()
        response: GenerateContentResponse = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        duration = time.perf_counter() - start

        # Emit metrics
        llm_request_duration_seconds.labels(provider="gemini", model=self.model_name).observe(
            duration
        )

        usage = response.usage_metadata
        if usage:
            input_tokens = usage.prompt_token_count or 0
            output_tokens = usage.candidates_token_count or 0
            llm_tokens_used_total.labels(
                provider="gemini", model=self.model_name, task_type=task_type
            ).inc(input_tokens + output_tokens)

            costs = _COST_PER_1K.get(self.model_name, {"input": 0.0, "output": 0.0})
            cost = (input_tokens / 1000 * costs["input"]) + (output_tokens / 1000 * costs["output"])
            llm_cost_usd_total.labels(provider="gemini", model=self.model_name).inc(cost)

        text = response.text
        logger.info(
            "gemini_generate",
            model=self.model_name,
            task_type=task_type,
            duration_s=round(duration, 3),
        )
        return text

    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict,
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> dict:
        """Generate JSON-structured output using Gemini's JSON mode."""
        import json

        model = genai.GenerativeModel(
            self.model_name,
            system_instruction=system_instruction
            or "You are a structured output generator. Always respond with valid JSON matching the provided schema.",
        )
        response = await model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=temperature,
                response_mime_type="application/json",
            ),
        )
        return json.loads(response.text)
