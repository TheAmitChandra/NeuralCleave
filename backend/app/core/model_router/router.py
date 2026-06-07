"""Model router — intelligent routing to the right LLM with automatic fallback chain.

Routing table:
  complex_reasoning  → Gemini Pro
  code_generation    → DeepSeek Coder
  summarization      → Gemini Flash
  embeddings         → sentence-transformers (local)
  cheap_inference    → Ollama (local)

Fallback chain: Gemini → DeepSeek → Ollama → DEGRADED MODE
"""

from __future__ import annotations

import structlog
from tenacity import RetryError, retry, stop_after_attempt, wait_exponential

from app.core.model_router.deepseek import DeepSeekClient
from app.core.model_router.gemini import GeminiClient
from app.core.model_router.ollama import OllamaClient
from app.core.model_router.token_budget import BudgetExceededError, TokenBudgetManager

logger = structlog.get_logger(__name__)

# Task type → preferred provider
_ROUTING_TABLE: dict[str, str] = {
    "complex_reasoning": "gemini_pro",
    "code_generation": "deepseek_coder",
    "code_review": "deepseek_coder",
    "summarization": "gemini_flash",
    "intent_extraction": "gemini_flash",
    "task_decomposition": "gemini_pro",
    "validation": "gemini_flash",
    "reflection": "gemini_flash",
    "cheap_inference": "ollama",
    "general": "gemini_flash",
}

# Providers in fallback order
_FALLBACK_ORDER = ["gemini_flash", "gemini_pro", "deepseek_coder", "ollama"]


class ModelRouter:
    """Central LLM router — picks the right model, falls back on failure."""

    def __init__(self, budget_manager: TokenBudgetManager | None = None) -> None:
        self._gemini_pro = GeminiClient(model="gemini-1.5-pro")
        self._gemini_flash = GeminiClient(model="gemini-2.0-flash")
        self._deepseek = DeepSeekClient(model="deepseek-coder")
        self._ollama = OllamaClient()
        self._budget = budget_manager or TokenBudgetManager()

    def _get_client(self, provider: str) -> GeminiClient | DeepSeekClient | OllamaClient:
        return {
            "gemini_pro": self._gemini_pro,
            "gemini_flash": self._gemini_flash,
            "deepseek_coder": self._deepseek,
            "ollama": self._ollama,
        }[provider]

    async def generate(
        self,
        prompt: str,
        task_type: str = "general",
        system_instruction: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 8192,
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
    ) -> str:
        """Route to the preferred provider and fall back down the chain on failure.

        When ``agent_id`` **and** ``task_id`` are both supplied, the call is
        budget-gated: ``BudgetExceededError`` is raised before any LLM call is
        made if the remaining token budget is insufficient.  Usage is recorded
        after a successful completion using the provider-reported token count.
        """
        preferred = _ROUTING_TABLE.get(task_type, "gemini_flash")

        # ---- Budget gate (opt-in: only when agent_id + task_id provided) ----
        if agent_id and task_id:
            try:
                await self._budget.check_and_reserve(
                    agent_id=agent_id,
                    task_id=task_id,
                    tokens=max_tokens,
                    auto_create=True,
                )
            except BudgetExceededError:
                raise  # propagate — callers decide whether to handle or abort

        # Build fallback list starting from the preferred provider
        providers = [preferred] + [p for p in _FALLBACK_ORDER if p != preferred]

        last_error: Exception | None = None
        for provider in providers:
            try:
                client = self._get_client(provider)
                logger.info("model_router_attempt", provider=provider, task_type=task_type)
                response = await client.generate(
                    prompt=prompt,
                    system_instruction=system_instruction,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    task_type=task_type,
                )
                # Record actual usage (best-effort — client may not expose counts)
                if agent_id and task_id:
                    tokens_used = getattr(client, "last_token_count", max_tokens)
                    try:
                        await self._budget.record_usage(
                            agent_id=agent_id,
                            task_id=task_id,
                            tokens_used=tokens_used,
                            model=provider,
                        )
                    except Exception:  # noqa: BLE001
                        pass  # observability failure must not break generation
                return response
            except BudgetExceededError:
                raise  # re-raise immediately — budget errors skip fallback
            except Exception as exc:
                logger.warning(
                    "model_router_provider_failed",
                    provider=provider,
                    error=str(exc),
                )
                last_error = exc

        # All providers exhausted → DEGRADED MODE
        logger.error("model_router_all_providers_failed", task_type=task_type)
        raise RuntimeError(
            f"All LLM providers failed for task_type='{task_type}'. Last error: {last_error}"
        )

    async def generate_structured(
        self,
        prompt: str,
        response_schema: dict,
        task_type: str = "general",
        system_instruction: str | None = None,
        temperature: float = 0.1,
    ) -> dict:
        """Generate structured JSON output — Gemini only (supports JSON mode natively)."""
        return await self._gemini_flash.generate_structured(
            prompt=prompt,
            response_schema=response_schema,
            system_instruction=system_instruction,
            temperature=temperature,
        )


_model_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """Return the process-level ModelRouter singleton (lazy init).

    Defers LLM client construction until first call so module import does not
    hit genai.configure() or network calls during test collection.
    """
    global _model_router
    if _model_router is None:
        _model_router = ModelRouter()
    return _model_router


# Convenience alias — keeps existing `from ... import model_router` callsites
# working: the name resolves to the same lazy singleton on first access.
class _LazyModelRouter:
    """Proxy that initialises the real ModelRouter on first attribute access."""

    def __getattr__(self, name: str):  # type: ignore[override]
        return getattr(get_model_router(), name)


model_router = _LazyModelRouter()
