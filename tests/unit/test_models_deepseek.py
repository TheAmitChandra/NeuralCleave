"""Unit tests for cortexflow.models.deepseek — DeepSeekProvider + DeepSeekResponse."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from cortexflow.models.deepseek import (
    DEEPSEEK_CODER,
    DEEPSEEK_CHAT,
    DEEPSEEK_REASONER,
    DeepSeekProvider,
    DeepSeekResponse,
    SUPPORTED_MODELS,
)


# ---------------------------------------------------------------------------
# DeepSeekResponse
# ---------------------------------------------------------------------------


def test_response_text():
    r = DeepSeekResponse(text="def foo(): pass", model=DEEPSEEK_CODER, usage={})
    assert r.text == "def foo(): pass"


def test_response_input_tokens():
    r = DeepSeekResponse(text="", model=DEEPSEEK_CODER, usage={"input_tokens": 20})
    assert r.input_tokens == 20


def test_response_output_tokens():
    r = DeepSeekResponse(text="", model=DEEPSEEK_CODER, usage={"output_tokens": 15})
    assert r.output_tokens == 15


def test_response_missing_usage_returns_zero():
    r = DeepSeekResponse(text="", model=DEEPSEEK_CODER, usage={})
    assert r.input_tokens == 0
    assert r.output_tokens == 0


# ---------------------------------------------------------------------------
# DeepSeekProvider — construction
# ---------------------------------------------------------------------------


def test_provider_is_configured_true():
    p = DeepSeekProvider(api_key="sk-ds-test")
    assert p.is_configured is True


def test_provider_is_configured_false():
    p = DeepSeekProvider(api_key="")
    assert p.is_configured is False


def test_provider_default_model_is_coder():
    p = DeepSeekProvider(api_key="sk-x")
    assert p.default_model == DEEPSEEK_CODER


def test_provider_custom_default_model():
    p = DeepSeekProvider(api_key="sk-x", default_model=DEEPSEEK_CHAT)
    assert p.default_model == DEEPSEEK_CHAT


def test_provider_env_fallback(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key-xyz")
    p = DeepSeekProvider()
    assert p.is_configured is True


def test_provider_get_supported_models():
    models = DeepSeekProvider.get_supported_models()
    assert isinstance(models, frozenset)
    assert DEEPSEEK_CODER in models
    assert DEEPSEEK_CHAT in models
    assert DEEPSEEK_REASONER in models


# ---------------------------------------------------------------------------
# SUPPORTED_MODELS immutability
# ---------------------------------------------------------------------------


def test_supported_models_immutable():
    with pytest.raises((AttributeError, TypeError)):
        SUPPORTED_MODELS.add("new-model")  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# generate — missing httpx raises RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_raises_if_httpx_not_installed():
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "httpx":
            raise ImportError("No module named 'httpx'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        p = DeepSeekProvider(api_key="sk-test")
        with pytest.raises(RuntimeError, match="httpx package required"):
            await p.generate("hello")


# ---------------------------------------------------------------------------
# generate — missing API key raises RuntimeError
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_raises_if_api_key_missing():
    p = DeepSeekProvider(api_key="")
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        await p.generate("hello")


# ---------------------------------------------------------------------------
# generate — success path (mocked httpx)
# ---------------------------------------------------------------------------


def _make_mock_httpx_response(content: str, model: str = DEEPSEEK_CODER) -> MagicMock:
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value={
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 25},
        "model": model,
    })
    return resp


@pytest.mark.asyncio
async def test_generate_returns_deepseek_response():
    mock_resp = _make_mock_httpx_response("def reverse(lst): return lst[::-1]")

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        p = DeepSeekProvider(api_key="sk-test")
        result = await p.generate("Write a Python function to reverse a list.")

    assert isinstance(result, DeepSeekResponse)
    assert "reverse" in result.text


@pytest.mark.asyncio
async def test_generate_passes_system_message():
    mock_resp = _make_mock_httpx_response("ok")

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        p = DeepSeekProvider(api_key="sk-test")
        await p.generate("prompt", system="You are a coding assistant.")

    call_kwargs = mock_client.post.call_args
    body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
    messages = body["messages"]
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"


@pytest.mark.asyncio
async def test_generate_uses_model_override():
    mock_resp = _make_mock_httpx_response("answer", model=DEEPSEEK_CHAT)

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        p = DeepSeekProvider(api_key="sk-test", default_model=DEEPSEEK_CODER)
        result = await p.generate("hi", model=DEEPSEEK_CHAT)

    call_kwargs = mock_client.post.call_args
    body = call_kwargs[1]["json"] if "json" in call_kwargs[1] else call_kwargs.kwargs["json"]
    assert body["model"] == DEEPSEEK_CHAT


@pytest.mark.asyncio
async def test_generate_usage_tokens():
    mock_resp = _make_mock_httpx_response("result")

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("httpx.AsyncClient", return_value=mock_client):
        p = DeepSeekProvider(api_key="sk-test")
        result = await p.generate("hi")

    assert result.input_tokens == 10
    assert result.output_tokens == 25
