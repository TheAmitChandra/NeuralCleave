"""Tests for the model router — GeminiClient, DeepSeekClient, OllamaClient, ModelRouter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.model_router.deepseek import DeepSeekClient
from app.core.model_router.gemini import GeminiClient
from app.core.model_router.ollama import OllamaClient
from app.core.model_router.router import (
    _FALLBACK_ORDER,
    _ROUTING_TABLE,
    ModelRouter,
)

# ===========================================================================
# Test helpers
# ===========================================================================


def _gemini_response(text: str, in_tokens: int = 10, out_tokens: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata = MagicMock()
    resp.usage_metadata.prompt_token_count = in_tokens
    resp.usage_metadata.candidates_token_count = out_tokens
    return resp


def _deepseek_response(content: str, prompt_tok: int = 10, comp_tok: int = 20) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message.content = content
    resp.usage = MagicMock()
    resp.usage.total_tokens = prompt_tok + comp_tok
    resp.usage.prompt_tokens = prompt_tok
    resp.usage.completion_tokens = comp_tok
    return resp


def _make_router() -> tuple[ModelRouter, dict[str, MagicMock]]:
    """Create a ModelRouter without calling __init__ (avoids API key checks)."""
    router = ModelRouter.__new__(ModelRouter)
    mocks: dict[str, MagicMock] = {
        "gemini_pro": MagicMock(),
        "gemini_flash": MagicMock(),
        "deepseek_coder": MagicMock(),
        "ollama": MagicMock(),
    }
    router._gemini_pro = mocks["gemini_pro"]
    router._gemini_flash = mocks["gemini_flash"]
    router._deepseek = mocks["deepseek_coder"]
    router._ollama = mocks["ollama"]
    return router, mocks


# ===========================================================================
# GeminiClient
# ===========================================================================


class TestGeminiClient:
    """Unit tests for GeminiClient."""

    def test_init_raises_if_no_api_key(self) -> None:
        with (
            patch("app.core.model_router.gemini.genai"),
            patch("app.core.model_router.gemini.settings") as mock_settings,
        ):
            mock_settings.GEMINI_API_KEY = ""
            with pytest.raises(ValueError, match="GEMINI_API_KEY"):
                GeminiClient(api_key=None)

    def test_init_configures_genai_with_provided_key(self) -> None:
        with patch("app.core.model_router.gemini.genai") as mock_genai:
            mock_genai.GenerativeModel.return_value = MagicMock()
            GeminiClient(api_key="my-test-key")
        mock_genai.configure.assert_called_once_with(api_key="my-test-key")

    async def test_generate_returns_response_text(self) -> None:
        with patch("app.core.model_router.gemini.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(
                return_value=_gemini_response("hello from gemini")
            )
            mock_genai.GenerativeModel.return_value = mock_model
            mock_genai.GenerationConfig = MagicMock()

            client = GeminiClient(api_key="key")
            result = await client.generate(prompt="say hello")

        assert result == "hello from gemini"

    async def test_generate_creates_new_model_when_system_instruction_given(self) -> None:
        with patch("app.core.model_router.gemini.genai") as mock_genai:
            sysmodel = MagicMock()
            sysmodel.generate_content_async = AsyncMock(
                return_value=_gemini_response("with system")
            )
            mock_genai.GenerativeModel.return_value = sysmodel
            mock_genai.GenerationConfig = MagicMock()

            client = GeminiClient(api_key="key")
            await client.generate(prompt="hi", system_instruction="be concise")

        # Called at least twice: once for init, once inside generate() with system_instruction
        assert mock_genai.GenerativeModel.call_count >= 2

    async def test_generate_handles_none_usage_metadata(self) -> None:
        resp = _gemini_response("ok")
        resp.usage_metadata = None

        with patch("app.core.model_router.gemini.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=resp)
            mock_genai.GenerativeModel.return_value = mock_model
            mock_genai.GenerationConfig = MagicMock()

            client = GeminiClient(api_key="key")
            result = await client.generate(prompt="test")

        assert result == "ok"

    async def test_generate_structured_parses_json_response(self) -> None:
        import json

        expected = {"answer": 42, "label": "correct"}
        mock_resp = MagicMock()
        mock_resp.text = json.dumps(expected)

        with patch("app.core.model_router.gemini.genai") as mock_genai:
            mock_model = MagicMock()
            mock_model.generate_content_async = AsyncMock(return_value=mock_resp)
            mock_genai.GenerativeModel.return_value = mock_model
            mock_genai.GenerationConfig = MagicMock()

            client = GeminiClient(api_key="key")
            result = await client.generate_structured(
                prompt="classify this",
                response_schema={"type": "object"},
            )

        assert result == expected


# ===========================================================================
# DeepSeekClient
# ===========================================================================


class TestDeepSeekClient:
    """Unit tests for DeepSeekClient."""

    def test_init_raises_if_no_api_key(self) -> None:
        with (
            patch("app.core.model_router.deepseek.AsyncOpenAI"),
            patch("app.core.model_router.deepseek.settings") as mock_settings,
        ):
            mock_settings.DEEPSEEK_API_KEY = ""
            with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
                DeepSeekClient(api_key=None)

    def test_default_model_name(self) -> None:
        with patch("app.core.model_router.deepseek.AsyncOpenAI"):
            client = DeepSeekClient(api_key="k")
        assert client.model_name == "deepseek-coder"

    async def test_generate_returns_completion_content(self) -> None:
        with patch("app.core.model_router.deepseek.AsyncOpenAI") as mock_cls:
            mock_oa = MagicMock()
            mock_cls.return_value = mock_oa
            mock_oa.chat.completions.create = AsyncMock(
                return_value=_deepseek_response("def greet(): pass")
            )

            client = DeepSeekClient(api_key="key")
            result = await client.generate(prompt="write a greet function")

        assert result == "def greet(): pass"

    async def test_generate_includes_system_message_when_provided(self) -> None:
        with patch("app.core.model_router.deepseek.AsyncOpenAI") as mock_cls:
            mock_oa = MagicMock()
            mock_cls.return_value = mock_oa
            mock_oa.chat.completions.create = AsyncMock(return_value=_deepseek_response("done"))

            client = DeepSeekClient(api_key="key")
            await client.generate(prompt="code", system_instruction="act as a coder")

        msgs = mock_oa.chat.completions.create.call_args.kwargs["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "act as a coder"
        assert msgs[1]["role"] == "user"

    async def test_generate_omits_system_message_when_not_provided(self) -> None:
        with patch("app.core.model_router.deepseek.AsyncOpenAI") as mock_cls:
            mock_oa = MagicMock()
            mock_cls.return_value = mock_oa
            mock_oa.chat.completions.create = AsyncMock(return_value=_deepseek_response("done"))

            client = DeepSeekClient(api_key="key")
            await client.generate(prompt="simple prompt")

        msgs = mock_oa.chat.completions.create.call_args.kwargs["messages"]
        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"


# ===========================================================================
# OllamaClient
# ===========================================================================


class TestOllamaClient:
    """Unit tests for OllamaClient."""

    def test_default_model_is_llama3(self) -> None:
        with patch("app.core.model_router.ollama.AsyncClient"):
            client = OllamaClient(base_url="http://localhost:11434")
        assert client.model_name == "llama3.2"

    def test_custom_model_name_stored(self) -> None:
        with patch("app.core.model_router.ollama.AsyncClient"):
            client = OllamaClient(base_url="http://localhost:11434", model="mistral")
        assert client.model_name == "mistral"

    async def test_generate_returns_message_content(self) -> None:
        with patch("app.core.model_router.ollama.AsyncClient") as mock_cls:
            mock_ac = MagicMock()
            mock_cls.return_value = mock_ac
            resp = MagicMock()
            resp.message.content = "Local LLM says hi"
            resp.eval_count = 12
            mock_ac.chat = AsyncMock(return_value=resp)

            client = OllamaClient(base_url="http://localhost:11434")
            result = await client.generate(prompt="hello")

        assert result == "Local LLM says hi"

    async def test_is_available_returns_true_when_server_reachable(self) -> None:
        with patch("app.core.model_router.ollama.AsyncClient") as mock_cls:
            mock_ac = MagicMock()
            mock_cls.return_value = mock_ac
            mock_ac.list = AsyncMock(return_value=[])

            client = OllamaClient(base_url="http://localhost:11434")
            result = await client.is_available()

        assert result is True

    async def test_is_available_returns_false_on_connection_error(self) -> None:
        with patch("app.core.model_router.ollama.AsyncClient") as mock_cls:
            mock_ac = MagicMock()
            mock_cls.return_value = mock_ac
            mock_ac.list = AsyncMock(side_effect=ConnectionRefusedError("refused"))

            client = OllamaClient(base_url="http://localhost:11434")
            result = await client.is_available()

        assert result is False


# ===========================================================================
# ModelRouter — client resolution
# ===========================================================================


class TestModelRouterClientResolution:
    """Tests for _get_client() provider dispatch."""

    def test_get_client_returns_gemini_pro(self) -> None:
        router, mocks = _make_router()
        assert router._get_client("gemini_pro") is mocks["gemini_pro"]

    def test_get_client_returns_gemini_flash(self) -> None:
        router, mocks = _make_router()
        assert router._get_client("gemini_flash") is mocks["gemini_flash"]

    def test_get_client_returns_deepseek(self) -> None:
        router, mocks = _make_router()
        assert router._get_client("deepseek_coder") is mocks["deepseek_coder"]

    def test_get_client_returns_ollama(self) -> None:
        router, mocks = _make_router()
        assert router._get_client("ollama") is mocks["ollama"]

    def test_get_client_unknown_provider_raises_key_error(self) -> None:
        router, _ = _make_router()
        with pytest.raises(KeyError):
            router._get_client("nonexistent")


# ===========================================================================
# ModelRouter — routing logic
# ===========================================================================


class TestModelRouterRouting:
    """Tests for generate() routing and fallback behaviour."""

    async def test_complex_reasoning_routes_to_gemini_pro(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_pro"].generate = AsyncMock(return_value="deep analysis")

        result = await router.generate(prompt="analyse X", task_type="complex_reasoning")

        assert result == "deep analysis"
        mocks["gemini_pro"].generate.assert_called_once()

    async def test_code_generation_routes_to_deepseek(self) -> None:
        router, mocks = _make_router()
        mocks["deepseek_coder"].generate = AsyncMock(return_value="def foo(): ...")

        result = await router.generate(prompt="write a function", task_type="code_generation")

        assert result == "def foo(): ..."
        mocks["deepseek_coder"].generate.assert_called_once()

    async def test_summarization_routes_to_gemini_flash(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_flash"].generate = AsyncMock(return_value="short summary")

        result = await router.generate(prompt="summarise doc", task_type="summarization")

        assert result == "short summary"
        mocks["gemini_flash"].generate.assert_called_once()

    async def test_unknown_task_type_defaults_to_gemini_flash(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_flash"].generate = AsyncMock(return_value="default")

        result = await router.generate(prompt="do something", task_type="__unknown__")

        assert result == "default"
        mocks["gemini_flash"].generate.assert_called_once()

    async def test_falls_back_on_primary_provider_failure(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_pro"].generate = AsyncMock(side_effect=RuntimeError("pro down"))
        mocks["gemini_flash"].generate = AsyncMock(return_value="flash fallback")

        result = await router.generate(prompt="test", task_type="complex_reasoning")

        assert result == "flash fallback"
        mocks["gemini_pro"].generate.assert_called_once()
        mocks["gemini_flash"].generate.assert_called_once()

    async def test_raises_runtime_error_when_all_providers_fail(self) -> None:
        router, mocks = _make_router()
        for m in mocks.values():
            m.generate = AsyncMock(side_effect=RuntimeError("down"))

        with pytest.raises(RuntimeError, match="All LLM providers failed"):
            await router.generate(prompt="test", task_type="general")

    async def test_generate_structured_always_uses_gemini_flash(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_flash"].generate_structured = AsyncMock(return_value={"ok": True})

        result = await router.generate_structured(
            prompt="structure it",
            response_schema={"type": "object"},
        )

        assert result == {"ok": True}
        mocks["gemini_flash"].generate_structured.assert_called_once()

    async def test_generate_passes_temperature_kwarg(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_flash"].generate = AsyncMock(return_value="ok")

        await router.generate(prompt="p", task_type="general", temperature=0.7)

        assert mocks["gemini_flash"].generate.call_args.kwargs["temperature"] == 0.7

    async def test_generate_passes_max_tokens_kwarg(self) -> None:
        router, mocks = _make_router()
        mocks["gemini_flash"].generate = AsyncMock(return_value="ok")

        await router.generate(prompt="p", task_type="general", max_tokens=256)

        assert mocks["gemini_flash"].generate.call_args.kwargs["max_tokens"] == 256


# ===========================================================================
# Routing table and fallback order
# ===========================================================================


class TestRoutingTable:
    """Tests for the static routing table and fallback constants."""

    def test_routing_table_covers_core_task_types(self) -> None:
        core_tasks = {
            "complex_reasoning",
            "code_generation",
            "code_review",
            "summarization",
            "cheap_inference",
            "general",
        }
        assert core_tasks.issubset(set(_ROUTING_TABLE.keys()))

    def test_cheap_inference_routes_to_ollama(self) -> None:
        assert _ROUTING_TABLE["cheap_inference"] == "ollama"

    def test_code_review_routes_to_deepseek(self) -> None:
        assert _ROUTING_TABLE["code_review"] == "deepseek_coder"

    def test_task_decomposition_routes_to_gemini_pro(self) -> None:
        assert _ROUTING_TABLE["task_decomposition"] == "gemini_pro"

    def test_fallback_order_has_four_providers(self) -> None:
        assert len(_FALLBACK_ORDER) == 4

    def test_fallback_order_starts_with_gemini_flash(self) -> None:
        assert _FALLBACK_ORDER[0] == "gemini_flash"

    def test_fallback_order_ends_with_ollama(self) -> None:
        assert _FALLBACK_ORDER[-1] == "ollama"
