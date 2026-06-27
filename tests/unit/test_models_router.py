"""Unit tests for cortexflow.models.router."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cortexflow_ai.models.router import (
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


@pytest.mark.asyncio
async def test_call_dispatches_deepseek_model() -> None:
    router = ModelRouter(deepseek_api_key="fake")
    mock_result = GenerationResult(text="c", model="deepseek-coder", provider="deepseek")

    with patch.object(router, "_deepseek", new=AsyncMock(return_value=mock_result)) as m:
        await router._call("deepseek-coder", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        m.assert_called_once()


@pytest.mark.asyncio
async def test_call_dispatches_openai_model() -> None:
    router = ModelRouter(openai_api_key="fake")
    mock_result = GenerationResult(text="d", model="gpt-4o", provider="openai")

    with patch.object(router, "_openai", new=AsyncMock(return_value=mock_result)) as m:
        await router._call("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)
        m.assert_called_once()


# ---------------------------------------------------------------------------
# Claude extended thinking
# ---------------------------------------------------------------------------


def _make_claude_mock(content_blocks, input_tokens: int = 10, output_tokens: int = 20):
    from unittest.mock import MagicMock

    response = MagicMock()
    response.content = content_blocks
    response.usage.input_tokens = input_tokens
    response.usage.output_tokens = output_tokens

    client = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    mock_anthropic = MagicMock()
    mock_anthropic.AsyncAnthropic = MagicMock(return_value=client)
    return mock_anthropic, client


def _make_block(block_type: str, **attrs):
    from unittest.mock import MagicMock

    block = MagicMock()
    block.type = block_type
    for key, value in attrs.items():
        setattr(block, key, value)
    return block


@pytest.mark.asyncio
async def test_claude_extended_thinking_sets_temperature_1_and_thinking_param() -> None:
    text_block = _make_block("text", text="Final answer.")
    thinking_block = _make_block("thinking", thinking="Reasoning trace...")
    mock_anthropic, client = _make_claude_mock([thinking_block, text_block])

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        router = ModelRouter(anthropic_api_key="sk-test")
        result = await router._claude(
            "claude-opus-4-8", prompt="think", system=None, max_tokens=2000,
            temperature=0.7, extended_thinking=True, thinking_budget_tokens=1000,
        )

    assert result.text == "Final answer."
    assert result.thinking == "Reasoning trace..."
    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["temperature"] == 1.0
    assert call_kwargs["thinking"] == {"type": "enabled", "budget_tokens": 1000}


@pytest.mark.asyncio
async def test_claude_without_extended_thinking_omits_thinking_param() -> None:
    text_block = _make_block("text", text="Plain answer.")
    mock_anthropic, client = _make_claude_mock([text_block])

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        router = ModelRouter(anthropic_api_key="sk-test")
        result = await router._claude(
            "claude-sonnet-4-6", prompt="hi", system=None, max_tokens=500, temperature=0.5,
        )

    assert result.text == "Plain answer."
    assert result.thinking is None
    call_kwargs = client.messages.create.call_args[1]
    assert "thinking" not in call_kwargs
    assert call_kwargs["temperature"] == 0.5


@pytest.mark.asyncio
async def test_claude_text_only_response_no_thinking_block() -> None:
    text_block = _make_block("text", text="No thinking here.")
    mock_anthropic, _client = _make_claude_mock([text_block])

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        router = ModelRouter(anthropic_api_key="sk-test")
        result = await router._claude(
            "claude-opus-4-8", prompt="hi", system=None, max_tokens=500,
            temperature=0.7, extended_thinking=True,
        )

    assert result.text == "No thinking here."
    assert result.thinking is None


@pytest.mark.asyncio
async def test_generate_passes_extended_thinking_through_to_claude() -> None:
    router = ModelRouter(anthropic_api_key="fake")
    mock_result = GenerationResult(text="ok", model=CLAUDE_OPUS, provider="anthropic", thinking="trace")

    with patch.object(router, "_claude", new=AsyncMock(return_value=mock_result)) as m:
        result = await router.generate(
            "analyze this in depth", task_type="complex_reasoning", extended_thinking=True,
        )

    assert result.thinking == "trace"
    call_kwargs = m.call_args[1]
    assert call_kwargs["extended_thinking"] is True


# ---------------------------------------------------------------------------
# _claude — missing-package / missing-key guards, system prompt
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_claude_raises_if_anthropic_not_installed() -> None:
    router = ModelRouter(anthropic_api_key="sk-test")
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("No module named 'anthropic'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install anthropic"):
            await router._claude(
                "claude-opus-4-8", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )


@pytest.mark.asyncio
async def test_claude_raises_if_no_api_key() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter(anthropic_api_key="")
    # Needs anthropic to "be installed" so the code reaches the API-key
    # check rather than failing on the import first.
    with patch.dict("sys.modules", {"anthropic": MagicMock()}):
        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            await router._claude(
                "claude-opus-4-8", prompt="hi", system=None, max_tokens=100, temperature=0.5,
            )


@pytest.mark.asyncio
async def test_claude_passes_system_prompt() -> None:
    text_block = _make_block("text", text="ok")
    mock_anthropic, client = _make_claude_mock([text_block])

    with patch.dict("sys.modules", {"anthropic": mock_anthropic}):
        router = ModelRouter(anthropic_api_key="sk-test")
        await router._claude(
            "claude-opus-4-8", prompt="hi", system="Be concise.", max_tokens=100, temperature=0.5,
        )

    call_kwargs = client.messages.create.call_args[1]
    assert call_kwargs["system"] == "Be concise."


# ---------------------------------------------------------------------------
# _gemini
# ---------------------------------------------------------------------------


def _mock_genai_module(response_text: str):
    from unittest.mock import MagicMock

    mock_genai = MagicMock()
    mock_genai.configure = MagicMock()
    mock_response = MagicMock()
    mock_response.text = response_text
    mock_gmodel = MagicMock()
    mock_gmodel.generate_content_async = AsyncMock(return_value=mock_response)
    mock_genai.GenerativeModel = MagicMock(return_value=mock_gmodel)
    mock_genai.GenerationConfig = MagicMock()
    return mock_genai, mock_gmodel


def _genai_sys_modules(mock_genai) -> dict:
    # `import google.generativeai as genai` resolves the alias via
    # getattr(google, "generativeai") through the import machinery's
    # dotted-alias handling, not via sys.modules["google.generativeai"]
    # directly — same gotcha as `import redis.asyncio as aioredis`.
    # Patching only the submodule entry leaves the parent's attribute
    # auto-generated and unrelated to our mock.
    from unittest.mock import MagicMock

    mock_google = MagicMock()
    mock_google.generativeai = mock_genai
    return {"google": mock_google, "google.generativeai": mock_genai}


@pytest.mark.asyncio
async def test_gemini_raises_if_not_installed() -> None:
    router = ModelRouter(gemini_api_key="sk-test")
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "google.generativeai":
            raise ImportError("No module named 'google.generativeai'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install google-generativeai"):
            await router._gemini(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)


@pytest.mark.asyncio
async def test_gemini_raises_if_no_api_key() -> None:
    router = ModelRouter(gemini_api_key="")
    mock_genai, _ = _mock_genai_module("unused")

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            await router._gemini(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)


@pytest.mark.asyncio
async def test_gemini_success_returns_text() -> None:
    router = ModelRouter(gemini_api_key="sk-test")
    mock_genai, mock_gmodel = _mock_genai_module("Gemini says hi")

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        result = await router._gemini(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)

    assert result.text == "Gemini says hi"
    assert result.provider == "google"
    mock_gmodel.generate_content_async.assert_called_once()


@pytest.mark.asyncio
async def test_gemini_prepends_system_prompt() -> None:
    router = ModelRouter(gemini_api_key="sk-test")
    mock_genai, mock_gmodel = _mock_genai_module("ok")

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        await router._gemini(GEMINI_FLASH, prompt="hi", system="Be terse.", max_tokens=100)

    call_args = mock_gmodel.generate_content_async.call_args[0]
    assert call_args[0] == "Be terse.\n\nhi"


@pytest.mark.asyncio
async def test_gemini_populates_usage_from_usage_metadata() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter(gemini_api_key="sk-test")
    mock_genai, mock_gmodel = _mock_genai_module("hi")
    mock_usage_metadata = MagicMock()
    mock_usage_metadata.prompt_token_count = 12
    mock_usage_metadata.candidates_token_count = 34
    mock_gmodel.generate_content_async.return_value.usage_metadata = mock_usage_metadata

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        result = await router._gemini(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)

    assert result.usage == {"input_tokens": 12, "output_tokens": 34}


@pytest.mark.asyncio
async def test_gemini_usage_empty_when_no_usage_metadata() -> None:
    router = ModelRouter(gemini_api_key="sk-test")
    mock_genai, mock_gmodel = _mock_genai_module("hi")
    mock_gmodel.generate_content_async.return_value.usage_metadata = None

    with patch.dict("sys.modules", _genai_sys_modules(mock_genai)):
        result = await router._gemini(GEMINI_FLASH, prompt="hi", system=None, max_tokens=100)

    assert result.usage == {}


# ---------------------------------------------------------------------------
# _deepseek
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_deepseek_raises_if_no_api_key() -> None:
    router = ModelRouter(deepseek_api_key="")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        await router._deepseek(DEEPSEEK_CODER, prompt="hi", system=None, max_tokens=100, temperature=0.5)


@pytest.mark.asyncio
async def test_deepseek_success_delegates_to_provider() -> None:
    from cortexflow_ai.models.deepseek import DeepSeekProvider, DeepSeekResponse

    router = ModelRouter(deepseek_api_key="sk-test")
    fake_response = DeepSeekResponse(text="coded it", model=DEEPSEEK_CODER, usage={"input_tokens": 1})

    with patch.object(DeepSeekProvider, "generate", new=AsyncMock(return_value=fake_response)):
        result = await router._deepseek(
            DEEPSEEK_CODER, prompt="write code", system=None, max_tokens=500, temperature=0.2,
        )

    assert result.text == "coded it"
    assert result.provider == "deepseek"
    assert result.usage == {"input_tokens": 1}


# ---------------------------------------------------------------------------
# _ollama
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ollama_raises_if_httpx_not_installed() -> None:
    router = ModelRouter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="pip install httpx"):
            await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=100)


@pytest.mark.asyncio
async def test_ollama_success_returns_response_text() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"response": "ollama says hi"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=100)

    assert result.text == "ollama says hi"
    assert result.provider == "ollama"


@pytest.mark.asyncio
async def test_ollama_prepends_system_prompt() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"response": "ok"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        await router._ollama("llama3.2", prompt="hi", system="Be terse.", max_tokens=100)

    sent_json = mock_client.post.call_args[1]["json"]
    assert sent_json["prompt"] == "Be terse.\n\nhi"


@pytest.mark.asyncio
async def test_ollama_populates_usage_from_eval_counts() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(
        return_value={"response": "hi", "prompt_eval_count": 8, "eval_count": 16}
    )

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=100)

    assert result.usage == {"input_tokens": 8, "output_tokens": 16}


@pytest.mark.asyncio
async def test_ollama_usage_empty_when_eval_counts_missing() -> None:
    from unittest.mock import MagicMock

    router = ModelRouter()

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"response": "hi"})

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await router._ollama("llama3.2", prompt="hi", system=None, max_tokens=100)

    assert result.usage == {}


# ---------------------------------------------------------------------------
# _openai
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_openai_raises_if_no_api_key() -> None:
    router = ModelRouter(openai_api_key="")
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await router._openai("gpt-4o", prompt="hi", system=None, max_tokens=100, temperature=0.5)


@pytest.mark.asyncio
async def test_openai_success_delegates_to_provider() -> None:
    from cortexflow_ai.models.openai_ import OpenAIProvider, OpenAIResponse

    router = ModelRouter(openai_api_key="sk-test")
    fake_response = OpenAIResponse(text="hi from gpt", model="gpt-4o", usage={"input_tokens": 2})

    with patch.object(OpenAIProvider, "generate", new=AsyncMock(return_value=fake_response)):
        result = await router._openai(
            "gpt-4o", prompt="hello", system=None, max_tokens=200, temperature=0.7,
        )

    assert result.text == "hi from gpt"
    assert result.provider == "openai"
    assert result.usage == {"input_tokens": 2}
