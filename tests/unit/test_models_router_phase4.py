"""Unit tests for Phase 4 ModelRouter additions: complexity detection, privacy mode, overrides."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cortexflow.models.router import (
    _COMPLEX_WORD_THRESHOLD,
    CLAUDE_OPUS,
    GEMINI_FLASH,
    OLLAMA_DEFAULT,
    ModelRouter,
    _detect_complexity,
)

# ---------------------------------------------------------------------------
# _detect_complexity
# ---------------------------------------------------------------------------


def test_short_prompt_is_cheap():
    assert _detect_complexity("hi") == "cheap_inference"


def test_short_question_is_cheap():
    assert _detect_complexity("what time is it") == "cheap_inference"


def test_keyword_analyze_is_complex():
    assert _detect_complexity("analyze the impact of AI on society") == "complex_reasoning"


def test_keyword_compare_is_complex():
    assert _detect_complexity("compare Redis and Memcached") == "complex_reasoning"


def test_keyword_explain_is_complex():
    assert _detect_complexity("explain how transformers work") == "complex_reasoning"


def test_keyword_tradeoffs_is_complex():
    assert _detect_complexity("what are the trade-offs of microservices") == "complex_reasoning"


def test_long_prompt_is_complex():
    long_text = " ".join(["word"] * (_COMPLEX_WORD_THRESHOLD + 10))
    assert _detect_complexity(long_text) == "complex_reasoning"


def test_medium_no_keywords_is_general():
    # 30-50 words, no complex keywords
    text = " ".join(["word"] * 35)
    assert _detect_complexity(text) == "general"


def test_empty_prompt_is_cheap():
    assert _detect_complexity("") == "cheap_inference"


def test_keyword_case_insensitive():
    assert _detect_complexity("ANALYZE the situation") == "complex_reasoning"


# ---------------------------------------------------------------------------
# Privacy mode
# ---------------------------------------------------------------------------


def test_privacy_mode_default_false():
    router = ModelRouter()
    assert router.privacy_mode is False


def test_privacy_mode_can_be_set():
    router = ModelRouter(privacy_mode=True)
    assert router.privacy_mode is True


@pytest.mark.asyncio
async def test_privacy_mode_routes_to_ollama():
    router = ModelRouter(privacy_mode=True)
    ollama_called_with = []

    async def _fake_call(model_id, **kwargs):
        ollama_called_with.append(model_id)
        result = MagicMock()
        result.text = "response"
        result.usage = {}
        return result

    router._call = _fake_call
    await router.generate("hello")

    assert len(ollama_called_with) == 1
    assert ollama_called_with[0] == OLLAMA_DEFAULT


@pytest.mark.asyncio
async def test_privacy_mode_ignores_task_type():
    router = ModelRouter(privacy_mode=True)
    called = []

    async def _fake_call(model_id, **kwargs):
        called.append(model_id)
        result = MagicMock()
        result.text = "resp"
        result.usage = {}
        return result

    router._call = _fake_call
    await router.generate("complex reasoning prompt", task_type="complex_reasoning")

    # Should still use Ollama, not Claude
    assert called[0] == OLLAMA_DEFAULT


# ---------------------------------------------------------------------------
# Per-channel override
# ---------------------------------------------------------------------------


def test_channel_overrides_empty_by_default():
    router = ModelRouter()
    assert router.channel_overrides == {}


def test_set_channel_override():
    router = ModelRouter()
    router.set_channel_override("telegram", GEMINI_FLASH)
    assert router.channel_overrides["telegram"] == GEMINI_FLASH


def test_clear_channel_override():
    router = ModelRouter(channel_overrides={"telegram": GEMINI_FLASH})
    router.clear_channel_override("telegram")
    assert "telegram" not in router.channel_overrides


def test_clear_nonexistent_override_no_error():
    router = ModelRouter()
    router.clear_channel_override("nonexistent")  # should not raise


@pytest.mark.asyncio
async def test_channel_override_routes_to_pinned_model():
    router = ModelRouter(channel_overrides={"telegram": GEMINI_FLASH})
    called = []

    async def _fake_call(model_id, **kwargs):
        called.append(model_id)
        result = MagicMock()
        result.text = "ok"
        result.usage = {}
        return result

    router._call = _fake_call
    await router.generate("hello", channel_id="telegram")

    assert called[0] == GEMINI_FLASH


@pytest.mark.asyncio
async def test_no_channel_override_uses_normal_routing():
    router = ModelRouter(channel_overrides={"telegram": GEMINI_FLASH})
    called = []

    async def _fake_call(model_id, **kwargs):
        called.append(model_id)
        result = MagicMock()
        result.text = "ok"
        result.usage = {}
        return result

    router._call = _fake_call
    # discord is NOT in overrides — should use normal routing
    await router.generate("hello", channel_id="discord", task_type="cheap_inference")

    assert called[0] == OLLAMA_DEFAULT  # cheap_inference primary


# ---------------------------------------------------------------------------
# Auto complexity
# ---------------------------------------------------------------------------


def test_auto_complexity_default_true():
    router = ModelRouter()
    assert router.auto_complexity is True


def test_auto_complexity_can_be_disabled():
    router = ModelRouter(auto_complexity=False)
    assert router.auto_complexity is False


@pytest.mark.asyncio
async def test_auto_complexity_upgrades_task_type():
    router = ModelRouter(auto_complexity=True)
    async def _tracked_call(model_id, **kwargs):
        result = MagicMock()
        result.text = "ok"
        result.usage = {}
        return result

    router._call = _tracked_call

    # "analyze" is a complexity keyword → should use complex_reasoning chain
    with patch.object(router, "_call", wraps=router._call) as mock_call:
        mock_call.return_value = MagicMock(text="ok", usage={})
        mock_call.side_effect = _tracked_call
        await router.generate("analyze the meaning of life in depth", task_type="general")
        # The first model tried should be CLAUDE_OPUS (complex_reasoning primary)
        assert mock_call.call_args_list[0][0][0] == CLAUDE_OPUS


@pytest.mark.asyncio
async def test_auto_complexity_disabled_no_upgrade():
    router = ModelRouter(auto_complexity=False)
    called_models = []

    async def _fake_call(model_id, **kwargs):
        called_models.append(model_id)
        result = MagicMock()
        result.text = "ok"
        result.usage = {}
        return result

    router._call = _fake_call
    await router.generate("analyze the meaning of life", task_type="general")
    # Without auto complexity, stays on general chain (GEMINI_FLASH)
    assert called_models[0] == GEMINI_FLASH
