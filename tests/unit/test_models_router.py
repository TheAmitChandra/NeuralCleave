"""Unit tests for cortexflow.models.router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cortexflow.models.router import (
    _ROUTING,
    CLAUDE_OPUS,
    DEEPSEEK_CODER,
    GEMINI_FLASH,
    OLLAMA_DEFAULT,
    GenerationResult,
    ModelRouter,
)

# ---------------------------------------------------------------------------
# Routing table
# ---------------------------------------------------------------------------


def test_routing_table_has_expected_task_types() -> None:
    required = {
        "complex_reasoning", "code_generation", "code_review",
        "summarization", "intent_extraction", "task_decomposition",
        "cheap_inference", "general",
    }
    assert required.issubset(_ROUTING.keys())


def test_complex_reasoning_primary_is_claude_opus() -> None:
    assert _ROUTING["complex_reasoning"][0] == CLAUDE_OPUS


def test_code_generation_primary_is_deepseek() -> None:
    assert _ROUTING["code_generation"][0] == DEEPSEEK_CODER


def test_cheap_inference_primary_is_ollama() -> None:
    assert _ROUTING["cheap_inference"][0] == OLLAMA_DEFAULT


def test_general_primary_is_gemini_flash() -> None:
    assert _ROUTING["general"][0] == GEMINI_FLASH


def test_every_chain_has_at_least_two_providers() -> None:
    for task, chain in _ROUTING.items():
        assert len(chain) >= 2, f"{task!r} chain too short: {chain}"


# ---------------------------------------------------------------------------
# GenerationResult
# ---------------------------------------------------------------------------


def test_generation_result_defaults() -> None:
    r = GenerationResult(text="hello", model="m", provider="p")
    assert r.usage == {}


def test_generation_result_with_usage() -> None:
    r = GenerationResult(text="hi", model="m", provider="p", usage={"input_tokens": 5})
    assert r.usage["input_tokens"] == 5


# ---------------------------------------------------------------------------
# ModelRouter.generate — mocked providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_returns_first_successful() -> None:
    router = ModelRouter()
    mock_result = GenerationResult(text="pong", model=GEMINI_FLASH, provider="google")

    with patch.object(router, "_gemini", new=AsyncMock(return_value=mock_result)):
        result = await router.generate("ping", task_type="general")

    assert result.text == "pong"
    assert result.provider == "google"


@pytest.mark.asyncio
async def test_generate_falls_back_on_primary_failure() -> None:
    router = ModelRouter()
    ollama_result = GenerationResult(text="from ollama", model=OLLAMA_DEFAULT, provider="ollama")

    async def _failing_gemini(*_, **__):
        raise RuntimeError("quota exceeded")

    with (
        patch.object(router, "_gemini", new=AsyncMock(side_effect=RuntimeError("quota exceeded"))),
        patch.object(router, "_ollama", new=AsyncMock(return_value=ollama_result)),
    ):
        result = await router.generate("hi", task_type="general")

    assert result.text == "from ollama"


@pytest.mark.asyncio
async def test_generate_raises_when_all_providers_fail() -> None:
    router = ModelRouter()

    with (
        patch.object(router, "_gemini", new=AsyncMock(side_effect=RuntimeError("fail1"))),
        patch.object(router, "_ollama", new=AsyncMock(side_effect=RuntimeError("fail2"))),
    ):
        with pytest.raises(RuntimeError, match="All providers exhausted"):
            await router.generate("hi", task_type="general")


@pytest.mark.asyncio
async def test_generate_unknown_task_type_uses_general_chain() -> None:
    router = ModelRouter()
    mock_result = GenerationResult(text="ok", model=GEMINI_FLASH, provider="google")

    with patch.object(router, "_gemini", new=AsyncMock(return_value=mock_result)):
        result = await router.generate("?", task_type="undefined_task_xyz")

    assert result.text == "ok"


# ---------------------------------------------------------------------------
# ModelRouter._call routing dispatch
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_dispatches_claude_model() -> None:
    router = ModelRouter(anthropic_api_key="fake")
    mock_result = GenerationResult(text="a", model="claude-opus-4-8", provider="anthropic")

    with patch.object(router, "_claude", new=AsyncMock(return_value=mock_result)) as m:
        await router._call("claude-opus-4-8", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_ollama_model() -> None:
    router = ModelRouter()
    mock_result = GenerationResult(text="b", model="llama3.2", provider="ollama")

    with patch.object(router, "_ollama", new=AsyncMock(return_value=mock_result)) as m:
        await router._call("ollama/llama3.2", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_raises_on_unknown_prefix() -> None:
    router = ModelRouter()
    with pytest.raises(ValueError, match="Unknown model prefix"):
        await router._call("unknown/model", prompt="hi", system=None, max_tokens=100, temperature=0.5)
