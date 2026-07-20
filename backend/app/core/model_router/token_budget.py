"""Token Budget Enforcement — NeuralCleave model router.

Provides per-agent, per-task token budget tracking backed by Redis.
The budget is checked BEFORE each LLM call and raises ``BudgetExceededError``
when the remaining budget is insufficient.

Public API
──────────
  TokenBudget          Pydantic model for a single budget record
  BudgetExceededError  Raised when a call would exceed the configured limit
  TokenBudgetManager   Redis-backed manager — create / update / reset / query
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Cost look-up table (USD per 1 k tokens — rough approximations)
# ---------------------------------------------------------------------------

_COST_PER_1K: dict[str, float] = {
    "gemini_pro": 0.0025,
    "gemini-1.5-pro": 0.0025,
    "gemini_flash": 0.00015,
    "gemini-2.0-flash": 0.00015,
    "deepseek_coder": 0.00014,
    "ollama": 0.0,  # local — no API cost
    "unknown": 0.0,
}


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class TokenBudget(BaseModel):
    """Snapshot of a budget record for a single (agent, task) pair."""

    agent_id: str
    task_id: str
    model: str = "unknown"
    max_tokens: int = Field(default=50_000, ge=1)
    used_tokens: int = Field(default=0, ge=0)
    max_cost_usd: float = Field(default=1.00, ge=0.0)
    estimated_cost_usd: float = Field(default=0.0, ge=0.0)
    alert_threshold_pct: float = Field(default=0.80, ge=0.0, le=1.0)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_updated: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def remaining_tokens(self) -> int:
        return max(0, self.max_tokens - self.used_tokens)

    @property
    def usage_pct(self) -> float:
        return self.used_tokens / self.max_tokens if self.max_tokens else 0.0

    @property
    def is_over_budget(self) -> bool:
        return self.used_tokens >= self.max_tokens or self.estimated_cost_usd >= self.max_cost_usd

    @property
    def is_near_limit(self) -> bool:
        return self.usage_pct >= self.alert_threshold_pct


class BudgetExceededError(Exception):
    """Raised when a requested LLM call would exceed the configured token budget."""

    def __init__(self, agent_id: str, task_id: str, requested: int, remaining: int) -> None:
        self.agent_id = agent_id
        self.task_id = task_id
        self.requested = requested
        self.remaining = remaining
        super().__init__(
            f"Token budget exceeded for agent={agent_id} task={task_id}: "
            f"requested={requested} remaining={remaining}"
        )


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

_DEFAULT_TTL_SECONDS = 86_400  # 24 h


class TokenBudgetManager:
    """Redis-backed manager for per-(agent, task) token budgets.

    Each budget is stored under the key ``budget:{agent_id}:{task_id}`` as a
    JSON-serialised ``TokenBudget``.  The key expires after 24 hours so stale
    budgets are cleaned up automatically.

    Usage::

        mgr = TokenBudgetManager()
        await mgr.create(agent_id="a1", task_id="t1", max_tokens=20_000)

        # Before each LLM call:
        await mgr.check_and_reserve(agent_id="a1", task_id="t1", tokens=1024)

        # After the call completes with the actual token count:
        await mgr.record_usage(agent_id="a1", task_id="t1", tokens_used=930, model="gemini_flash")
    """

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url  # resolved lazily so tests can patch

    async def _get_redis(self):  # type: ignore[return]
        """Lazily connect to Redis."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import]

            url = self._redis_url
            if url is None:
                from app.config import get_settings

                url = get_settings().REDIS_URL
            return await aioredis.from_url(url, decode_responses=True)
        except ImportError as exc:
            raise RuntimeError("redis package required: pip install redis") from exc

    @staticmethod
    def _key(agent_id: str, task_id: str) -> str:
        return f"budget:{agent_id}:{task_id}"

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    async def create(
        self,
        agent_id: str,
        task_id: str,
        max_tokens: int = 50_000,
        max_cost_usd: float = 1.00,
        model: str = "unknown",
        alert_threshold_pct: float = 0.80,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> TokenBudget:
        """Create a new budget record.  Overwrites any existing record."""
        budget = TokenBudget(
            agent_id=agent_id,
            task_id=task_id,
            model=model,
            max_tokens=max_tokens,
            max_cost_usd=max_cost_usd,
            alert_threshold_pct=alert_threshold_pct,
        )
        await self._save(budget, ttl_seconds=ttl_seconds)
        logger.info(
            "budget.created",
            agent_id=agent_id,
            task_id=task_id,
            max_tokens=max_tokens,
        )
        return budget

    async def get(self, agent_id: str, task_id: str) -> TokenBudget | None:
        """Return the current budget record, or ``None`` if not found."""
        r = await self._get_redis()
        try:
            raw = await r.get(self._key(agent_id, task_id))
            if raw is None:
                return None
            return TokenBudget(**json.loads(raw))
        finally:
            await r.aclose()

    async def check_and_reserve(
        self,
        agent_id: str,
        task_id: str,
        tokens: int,
        *,
        auto_create: bool = True,
        max_tokens: int = 50_000,
    ) -> TokenBudget:
        """Check that ``tokens`` fit within the remaining budget.

        Raises ``BudgetExceededError`` if the budget is exhausted.
        If no budget record exists and ``auto_create=True``, one is created on
        the fly with the supplied ``max_tokens``.

        Parameters
        ----------
        agent_id, task_id:
            Identify the budget record.
        tokens:
            Number of tokens the upcoming LLM call will request.
        auto_create:
            Create a budget record if none exists yet.
        max_tokens:
            Used only when ``auto_create=True`` to set the new record's limit.

        Returns the budget *before* the reservation is recorded (the call is
        only reservation — use :meth:`record_usage` after the call completes).
        """
        budget = await self.get(agent_id, task_id)
        if budget is None:
            if not auto_create:
                raise KeyError(
                    f"No budget found for agent={agent_id} task={task_id}. "
                    "Create one first or pass auto_create=True."
                )
            budget = await self.create(
                agent_id=agent_id,
                task_id=task_id,
                max_tokens=max_tokens,
            )

        if budget.remaining_tokens < tokens:
            logger.warning(
                "budget.exceeded",
                agent_id=agent_id,
                task_id=task_id,
                requested=tokens,
                remaining=budget.remaining_tokens,
            )
            raise BudgetExceededError(
                agent_id=agent_id,
                task_id=task_id,
                requested=tokens,
                remaining=budget.remaining_tokens,
            )

        if budget.is_near_limit:
            logger.warning(
                "budget.near_limit",
                agent_id=agent_id,
                task_id=task_id,
                used_pct=round(budget.usage_pct * 100, 1),
            )

        return budget

    async def record_usage(
        self,
        agent_id: str,
        task_id: str,
        tokens_used: int,
        model: str = "unknown",
    ) -> TokenBudget:
        """Add ``tokens_used`` to the budget's running total.

        Also updates the estimated cost based on the model's rate table.
        Creates the budget record automatically if it does not yet exist.
        """
        budget = await self.get(agent_id, task_id)
        if budget is None:
            budget = await self.create(agent_id=agent_id, task_id=task_id)

        cost_per_token = _COST_PER_1K.get(model, _COST_PER_1K["unknown"]) / 1000.0
        budget = budget.model_copy(
            update={
                "used_tokens": budget.used_tokens + tokens_used,
                "estimated_cost_usd": budget.estimated_cost_usd + tokens_used * cost_per_token,
                "model": model,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )

        await self._save(budget)
        logger.info(
            "budget.usage_recorded",
            agent_id=agent_id,
            task_id=task_id,
            tokens_used=tokens_used,
            total_used=budget.used_tokens,
            model=model,
        )
        return budget

    async def reset(self, agent_id: str, task_id: str) -> None:
        """Reset usage counters (tokens + cost) back to zero."""
        budget = await self.get(agent_id, task_id)
        if budget is None:
            return
        budget = budget.model_copy(
            update={
                "used_tokens": 0,
                "estimated_cost_usd": 0.0,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }
        )
        await self._save(budget)
        logger.info("budget.reset", agent_id=agent_id, task_id=task_id)

    async def delete(self, agent_id: str, task_id: str) -> None:
        """Delete the budget record entirely."""
        r = await self._get_redis()
        try:
            await r.delete(self._key(agent_id, task_id))
        finally:
            await r.aclose()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _save(
        self,
        budget: TokenBudget,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        r = await self._get_redis()
        try:
            await r.set(
                self._key(budget.agent_id, budget.task_id),
                budget.model_dump_json(),
                ex=ttl_seconds,
            )
        finally:
            await r.aclose()


# ---------------------------------------------------------------------------
# Module-level singleton — import and use across the application
# ---------------------------------------------------------------------------

budget_manager = TokenBudgetManager()
