"""Ollama local inference client — air-gapped / offline mode."""

import time

import structlog
from ollama import AsyncClient

from app.config import get_settings
from app.core.observability.metrics import llm_request_duration_seconds, llm_tokens_used_total

logger = structlog.get_logger(__name__)
settings = get_settings()

_DEFAULT_MODEL = "llama3.2"


class OllamaClient:
    """Async wrapper around Ollama local inference server."""

    def __init__(self, base_url: str | None = None, model: str = _DEFAULT_MODEL) -> None:
        self._client = AsyncClient(host=base_url or settings.OLLAMA_BASE_URL)
        self.model_name = model

    async def generate(
        self,
        prompt: str,
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        task_type: str = "general",
    ) -> str:
        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        start = time.perf_counter()
        response = await self._client.chat(
            model=self.model_name,
            messages=messages,
            options={"temperature": temperature, "num_predict": max_tokens},
        )
        duration = time.perf_counter() - start

        llm_request_duration_seconds.labels(provider="ollama", model=self.model_name).observe(
            duration
        )

        content = response.message.content or ""
        # Ollama doesn't always return token counts — best-effort
        if hasattr(response, "eval_count") and response.eval_count:
            llm_tokens_used_total.labels(
                provider="ollama", model=self.model_name, task_type=task_type
            ).inc(response.eval_count)

        logger.info("ollama_generate", model=self.model_name, duration_s=round(duration, 3))
        return content

    async def is_available(self) -> bool:
        """Check if the Ollama server is reachable."""
        try:
            await self._client.list()
            return True
        except Exception:
            return False
