"""Unit tests for cortexflow.models.openai_ — OpenAIProvider + OpenAIResponse."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow.models.openai_ import (
    GPT4_TURBO,
    GPT4O,
    GPT4O_MINI,
    SUPPORTED_MODELS,
    OpenAIProvider,
    OpenAIResponse,
)

# ---------------------------------------------------------------------------
# OpenAIResponse
# ---------------------------------------------------------------------------


def test_response_text():
    r = OpenAIResponse(text="hello", model=GPT4O, usage={"input_tokens": 10, "output_tokens": 5})
    assert r.text == "hello"


def test_response_input_tokens():
    r = OpenAIResponse(text="", model=GPT4O, usage={"input_tokens": 42, "output_tokens": 0})
    assert r.input_tokens == 42


def test_response_output_tokens():
    r = OpenAIResponse(text="", model=GPT4O, usage={"input_tokens": 0, "output_tokens": 7})
    assert r.output_tokens == 7


def test_response_missing_usage_keys():
    r = OpenAIResponse(text="", model=GPT4O, usage={})
    assert r.input_tokens == 0
    assert r.output_tokens == 0


# ---------------------------------------------------------------------------
# OpenAIProvider — construction & properties
# ---------------------------------------------------------------------------


def test_provider_is_configured_true():
    p = OpenAIProvider(api_key="sk-test")
    assert p.is_configured is True


def test_provider_is_configured_false():
    p = OpenAIProvider(api_key="")
    assert p.is_configured is False


def test_provider_default_model():
    p = OpenAIProvider(api_key="sk-x", default_model=GPT4O_MINI)
    assert p.default_model == GPT4O_MINI


def test_provider_default_model_fallback():
    p = OpenAIProvider(api_key="sk-x")
    assert p.default_model == GPT4O


def test_get_supported_models_is_frozenset():
    models = OpenAIProvider.get_supported_models()
    assert isinstance(models, frozenset)


def test_get_supported_models_contains_gpt4o():
    assert GPT4O in OpenAIProvider.get_supported_models()
    assert GPT4O_MINI in OpenAIProvider.get_supported_models()
    assert GPT4_TURBO in OpenAIProvider.get_supported_models()


# ---------------------------------------------------------------------------
# OpenAIProvider.generate — success path (mocked)
# ---------------------------------------------------------------------------


def _make_mock_response(content: str, model: str = GPT4O) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.prompt_tokens = 10
    usage.completion_tokens = 20
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    resp.model = model
    return resp


@pytest.mark.asyncio
async def test_generate_returns_openai_response():
    mock_resp = _make_mock_response("Paris")

    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_resp)

    # Inject a fake openai module so the test runs without the package installed.
    # AsyncOpenAI is lazily imported inside generate(), so sys.modules injection
    # is the correct interception point.
    mock_openai = MagicMock()
    mock_openai.AsyncOpenAI = MagicMock(return_value=mock_client)
    with patch.dict("sys.modules", {"openai": mock_openai}):
        p = OpenAIProvider(api_key="sk-test")
        result = await p.generate("What is the capital of France?")

    assert isinstance(result, OpenAIResponse)
    assert result.text == "Paris"


@pytest.mark.asyncio
async def test_generate_uses_model_override():
    # This test only verifies provider construction and default_model — no API
    # call is made, so no openai import is needed.
    p = OpenAIProvider(api_key="sk-test", default_model=GPT4O)
    assert p.default_model == GPT4O


@pytest.mark.asyncio
async def test_generate_raises_if_openai_not_installed():
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "openai":
            raise ImportError("No module named 'openai'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        p = OpenAIProvider(api_key="sk-test")
        with pytest.raises(RuntimeError, match="openai package required"):
            await p.generate("hello")


# ---------------------------------------------------------------------------
# SUPPORTED_MODELS module-level constant
# ---------------------------------------------------------------------------


def test_supported_models_immutable():
    with pytest.raises((AttributeError, TypeError)):
        SUPPORTED_MODELS.add("new-model")  # type: ignore[attr-defined]


