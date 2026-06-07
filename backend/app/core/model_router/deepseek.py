"""DeepSeek API client — OpenAI-compatible, used for code generation."""

import time

import structlog
from openai import AsyncOpenAI

from app.config import get_settings
from app.core.observability.metrics import (
    llm_cost_usd_total,
    llm_request_duration_seconds,
    llm_tokens_used_total,
)

logger = structlog.get_logger(__name__)
settings = get_settings()

_DEFAULT_MODEL = "deepseek-coder"
_COST_PER_1K: dict[str, dict[str, float]] = {
    "deepseek-coder": {"input": 0.00014, "output": 0.00028},
    "deepseek-chat": {"input": 0.00014, "output": 0.00028},
}


class DeepSeekClient:
    """Async wrapper around DeepSeek's OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        key = api_key or settings.DEEPSEEK_API_KEY
        if not key:
            raise ValueError("DEEPSEEK_API_KEY is not configured")
        self._client = AsyncOpenAI(api_key=key, base_url="https://api.deepseek.com/v1")
        self.model_name = model

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 8192,
        task_type: str = "code_generation",
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        response = await self._client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        duration = time.perf_counter() - start

        llm_request_duration_seconds.labels(provider="deepseek", model=self.model_name).observe(
            duration
        )

        usage = response.usage
        if usage:
            llm_tokens_used_total.labels(
                provider="deepseek", model=self.model_name, task_type=task_type
            ).inc(usage.total_tokens)
            costs = _COST_PER_1K.get(self.model_name, {"input": 0.0, "output": 0.0})
            cost = (usage.prompt_tokens / 1000 * costs["input"]) + (
                usage.completion_tokens / 1000 * costs["output"]
            )
            llm_cost_usd_total.labels(provider="deepseek", model=self.model_name).inc(cost)

        content = response.choices[0].message.content or ""
        logger.info("deepseek_generate", model=self.model_name, duration_s=round(duration, 3))
        return content
