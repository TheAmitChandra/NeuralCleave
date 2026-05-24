"""Unit tests for the token budget system (token_budget.py) and its
integration with ModelRouter (router.py).

All Redis calls are fully mocked — no actual Redis connection needed.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.model_router.token_budget import (
    BudgetExceededError,
    TokenBudget,
    TokenBudgetManager,
    _COST_PER_1K,
)


# ===========================================================================
# TokenBudget model tests
# ===========================================================================


class TestTokenBudget:
    def test_remaining_tokens(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=10_000, used_tokens=3_000)
        assert b.remaining_tokens == 7_000

    def test_remaining_tokens_never_negative(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=1_000, used_tokens=2_000)
        assert b.remaining_tokens == 0

    def test_usage_pct(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=10_000, used_tokens=8_000)
        assert abs(b.usage_pct - 0.8) < 1e-9

    def test_usage_pct_zero_max(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=1, used_tokens=0)
        assert b.usage_pct == 0.0

    def test_is_over_budget_by_tokens(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=100, used_tokens=100)
        assert b.is_over_budget is True

    def test_is_over_budget_by_cost(self):
        b = TokenBudget(
            agent_id="a1",
            task_id="t1",
            max_tokens=100_000,
            used_tokens=0,
            max_cost_usd=0.50,
            estimated_cost_usd=0.50,
        )
        assert b.is_over_budget is True

    def test_not_over_budget(self):
        b = TokenBudget(agent_id="a1", task_id="t1", max_tokens=10_000, used_tokens=5_000)
        assert b.is_over_budget is False

    def test_is_near_limit_at_threshold(self):
        b = TokenBudget(
            agent_id="a1",
            task_id="t1",
            max_tokens=10_000,
            used_tokens=8_000,
            alert_threshold_pct=0.80,
        )
        assert b.is_near_limit is True

    def test_not_near_limit(self):
        b = TokenBudget(
            agent_id="a1",
            task_id="t1",
            max_tokens=10_000,
            used_tokens=7_999,
            alert_threshold_pct=0.80,
        )
        assert b.is_near_limit is False

    def test_default_values(self):
        b = TokenBudget(agent_id="x", task_id="y")
        assert b.max_tokens == 50_000
        assert b.used_tokens == 0
        assert b.max_cost_usd == 1.00
        assert b.alert_threshold_pct == 0.80
        assert b.model == "unknown"


# ===========================================================================
# BudgetExceededError tests
# ===========================================================================


class TestBudgetExceededError:
    def test_error_attributes(self):
        err = BudgetExceededError(agent_id="a1", task_id="t1", requested=500, remaining=100)
        assert err.agent_id == "a1"
        assert err.task_id == "t1"
        assert err.requested == 500
        assert err.remaining == 100

    def test_error_message_contains_key_info(self):
        err = BudgetExceededError(agent_id="a1", task_id="t1", requested=500, remaining=100)
        msg = str(err)
        assert "a1" in msg
        assert "t1" in msg
        assert "500" in msg
        assert "100" in msg

    def test_is_exception_subclass(self):
        assert issubclass(BudgetExceededError, Exception)


# ===========================================================================
# Helpers for mocking Redis
# ===========================================================================


def _make_mock_redis(stored: dict | None = None) -> MagicMock:
    """Return a mock that behaves like an aioredis client.

    ``stored`` is a dict mapping key → JSON string (simulates Redis GET).
    """
    storage: dict[str, str] = dict(stored or {})
    mock = MagicMock()
    mock.__aenter__ = AsyncMock(return_value=mock)
    mock.__aexit__ = AsyncMock(return_value=False)

    async def _get(key):
        return storage.get(key)

    async def _set(key, value, ex=None):
        storage[key] = value

    async def _delete(key):
        storage.pop(key, None)

    mock.get = AsyncMock(side_effect=_get)
    mock.set = AsyncMock(side_effect=_set)
    mock.delete = AsyncMock(side_effect=_delete)
    mock.aclose = AsyncMock()
    return mock, storage


# ===========================================================================
# TokenBudgetManager tests
# ===========================================================================


class TestTokenBudgetManagerCreate:
    @pytest.mark.asyncio
    async def test_create_returns_budget(self):
        mock_r, storage = _make_mock_redis()
        mgr = TokenBudgetManager(redis_url="redis://localhost:6379/0")

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.create(agent_id="a1", task_id="t1", max_tokens=20_000)

        assert isinstance(result, TokenBudget)
        assert result.agent_id == "a1"
        assert result.task_id == "t1"
        assert result.max_tokens == 20_000
        assert result.used_tokens == 0

    @pytest.mark.asyncio
    async def test_create_stores_in_redis(self):
        mock_r, storage = _make_mock_redis()
        mgr = TokenBudgetManager(redis_url="redis://localhost:6379/0")

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            await mgr.create(agent_id="a1", task_id="t1", max_tokens=30_000)

        key = "budget:a1:t1"
        assert key in storage
        stored = json.loads(storage[key])
        assert stored["max_tokens"] == 30_000


class TestTokenBudgetManagerGet:
    @pytest.mark.asyncio
    async def test_get_existing_budget(self):
        budget = TokenBudget(agent_id="a1", task_id="t1", max_tokens=5_000)
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.get("a1", "t1")

        assert result is not None
        assert result.max_tokens == 5_000

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self):
        mock_r, _ = _make_mock_redis()
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.get("no_agent", "no_task")

        assert result is None


class TestTokenBudgetManagerCheckAndReserve:
    @pytest.mark.asyncio
    async def test_check_passes_when_within_budget(self):
        budget = TokenBudget(agent_id="a1", task_id="t1", max_tokens=10_000, used_tokens=0)
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.check_and_reserve("a1", "t1", tokens=1_000)

        assert result.remaining_tokens == 10_000  # unchanged — reservation only checks

    @pytest.mark.asyncio
    async def test_check_raises_when_over_budget(self):
        budget = TokenBudget(agent_id="a1", task_id="t1", max_tokens=500, used_tokens=400)
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            with pytest.raises(BudgetExceededError) as exc_info:
                await mgr.check_and_reserve("a1", "t1", tokens=200)

        assert exc_info.value.requested == 200
        assert exc_info.value.remaining == 100

    @pytest.mark.asyncio
    async def test_auto_create_when_no_budget_exists(self):
        mock_r, storage = _make_mock_redis()
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.check_and_reserve(
                "new_agent", "new_task", tokens=100, auto_create=True, max_tokens=5_000
            )

        assert result.max_tokens == 5_000

    @pytest.mark.asyncio
    async def test_raises_key_error_when_no_budget_and_no_auto_create(self):
        mock_r, _ = _make_mock_redis()
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            with pytest.raises(KeyError):
                await mgr.check_and_reserve(
                    "no_agent", "no_task", tokens=100, auto_create=False
                )


class TestTokenBudgetManagerRecordUsage:
    @pytest.mark.asyncio
    async def test_record_usage_increments_tokens(self):
        budget = TokenBudget(agent_id="a1", task_id="t1", max_tokens=10_000, used_tokens=1_000)
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.record_usage("a1", "t1", tokens_used=500, model="gemini_flash")

        assert result.used_tokens == 1_500

    @pytest.mark.asyncio
    async def test_record_usage_calculates_cost(self):
        budget = TokenBudget(agent_id="a1", task_id="t1")
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.record_usage("a1", "t1", tokens_used=1_000, model="gemini_flash")

        expected_cost = _COST_PER_1K["gemini_flash"] / 1000.0 * 1_000
        assert abs(result.estimated_cost_usd - expected_cost) < 1e-9

    @pytest.mark.asyncio
    async def test_record_usage_creates_budget_if_missing(self):
        mock_r, _ = _make_mock_redis()
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            result = await mgr.record_usage("new_a", "new_t", tokens_used=200)

        assert result.used_tokens == 200


class TestTokenBudgetManagerReset:
    @pytest.mark.asyncio
    async def test_reset_clears_usage(self):
        budget = TokenBudget(
            agent_id="a1",
            task_id="t1",
            used_tokens=9_999,
            estimated_cost_usd=0.99,
        )
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            await mgr.reset("a1", "t1")
            result = await mgr.get("a1", "t1")

        assert result is not None
        assert result.used_tokens == 0
        assert result.estimated_cost_usd == 0.0

    @pytest.mark.asyncio
    async def test_reset_nonexistent_budget_is_noop(self):
        mock_r, _ = _make_mock_redis()
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            # Must not raise
            await mgr.reset("ghost", "phantom")


class TestTokenBudgetManagerDelete:
    @pytest.mark.asyncio
    async def test_delete_removes_key(self):
        budget = TokenBudget(agent_id="a1", task_id="t1")
        storage = {"budget:a1:t1": budget.model_dump_json()}
        mock_r, _ = _make_mock_redis(stored=storage)
        mgr = TokenBudgetManager()

        with patch.object(mgr, "_get_redis", AsyncMock(return_value=mock_r)):
            await mgr.delete("a1", "t1")
            result = await mgr.get("a1", "t1")

        assert result is None


# ===========================================================================
# ModelRouter + budget integration tests
# ===========================================================================


class TestModelRouterBudgetIntegration:
    @pytest.mark.asyncio
    async def test_generate_without_agent_id_skips_budget(self):
        from app.core.model_router.router import ModelRouter

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value="hello world")

        mock_budget_mgr = MagicMock()
        mock_budget_mgr.check_and_reserve = AsyncMock()
        mock_budget_mgr.record_usage = AsyncMock()

        router = ModelRouter(budget_manager=mock_budget_mgr)
        router._gemini_flash = mock_client

        result = await router.generate("test prompt")

        # No agent_id → budget methods must NOT be called
        mock_budget_mgr.check_and_reserve.assert_not_called()
        assert result == "hello world"

    @pytest.mark.asyncio
    async def test_generate_with_agent_id_checks_budget(self):
        from app.core.model_router.router import ModelRouter

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value="ok")

        mock_budget_mgr = MagicMock()
        dummy_budget = TokenBudget(agent_id="a1", task_id="t1", max_tokens=50_000)
        mock_budget_mgr.check_and_reserve = AsyncMock(return_value=dummy_budget)
        mock_budget_mgr.record_usage = AsyncMock(return_value=dummy_budget)

        router = ModelRouter(budget_manager=mock_budget_mgr)
        router._gemini_flash = mock_client

        await router.generate("test prompt", agent_id="a1", task_id="t1")

        mock_budget_mgr.check_and_reserve.assert_called_once_with(
            agent_id="a1",
            task_id="t1",
            tokens=8192,  # default max_tokens
            auto_create=True,
        )

    @pytest.mark.asyncio
    async def test_generate_raises_budget_exceeded_error(self):
        from app.core.model_router.router import ModelRouter
        from app.core.model_router.token_budget import BudgetExceededError

        mock_budget_mgr = MagicMock()
        mock_budget_mgr.check_and_reserve = AsyncMock(
            side_effect=BudgetExceededError(
                agent_id="a1", task_id="t1", requested=8192, remaining=100
            )
        )

        router = ModelRouter(budget_manager=mock_budget_mgr)

        with pytest.raises(BudgetExceededError) as exc_info:
            await router.generate("test", agent_id="a1", task_id="t1")

        assert exc_info.value.remaining == 100

    @pytest.mark.asyncio
    async def test_generate_records_usage_after_success(self):
        from app.core.model_router.router import ModelRouter

        mock_client = MagicMock()
        mock_client.generate = AsyncMock(return_value="response text")
        mock_client.last_token_count = 512

        mock_budget_mgr = MagicMock()
        dummy_budget = TokenBudget(agent_id="a1", task_id="t1")
        mock_budget_mgr.check_and_reserve = AsyncMock(return_value=dummy_budget)
        mock_budget_mgr.record_usage = AsyncMock(return_value=dummy_budget)

        router = ModelRouter(budget_manager=mock_budget_mgr)
        router._gemini_flash = mock_client

        await router.generate("prompt", agent_id="a1", task_id="t1")

        mock_budget_mgr.record_usage.assert_called_once()
        call_kwargs = mock_budget_mgr.record_usage.call_args[1]
        assert call_kwargs["agent_id"] == "a1"
        assert call_kwargs["task_id"] == "t1"
        assert call_kwargs["tokens_used"] == 512

    @pytest.mark.asyncio
    async def test_budget_exceeded_skips_fallback_chain(self):
        """BudgetExceededError must propagate immediately — no fallback retries."""
        from app.core.model_router.router import ModelRouter
        from app.core.model_router.token_budget import BudgetExceededError

        check_calls = 0

        async def _check(*args, **kwargs):
            nonlocal check_calls
            check_calls += 1
            raise BudgetExceededError("a1", "t1", 8192, 0)

        mock_budget_mgr = MagicMock()
        mock_budget_mgr.check_and_reserve = AsyncMock(side_effect=_check)

        router = ModelRouter(budget_manager=mock_budget_mgr)

        with pytest.raises(BudgetExceededError):
            await router.generate("prompt", agent_id="a1", task_id="t1")

        # Budget was checked exactly once — no retry loop attempted
        assert check_calls == 1
