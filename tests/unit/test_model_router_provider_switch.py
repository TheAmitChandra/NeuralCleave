"""Tests for ModelRouter._forced_provider — dynamic provider override."""

from __future__ import annotations

from cortexflow_ai.models.router import (
    _PROVIDER_TO_MODEL,
    CLAUDE_SONNET,
    DEEPSEEK_CODER,
    GEMINI_FLASH,
    GPT4O_MINI,
    OLLAMA_DEFAULT,
    ModelRouter,
)

# ---------------------------------------------------------------------------
# _forced_provider attribute
# ---------------------------------------------------------------------------


def test_forced_provider_starts_as_none():
    router = ModelRouter()
    assert router._forced_provider is None


def test_forced_provider_can_be_set():
    router = ModelRouter()
    router._forced_provider = "gemini"
    assert router._forced_provider == "gemini"


def test_forced_provider_can_be_cleared():
    router = ModelRouter()
    router._forced_provider = "gemini"
    router._forced_provider = None
    assert router._forced_provider is None


# ---------------------------------------------------------------------------
# _resolve_chain with _forced_provider
# ---------------------------------------------------------------------------


def test_resolve_chain_forced_gemini_leads():
    router = ModelRouter()
    router._forced_provider = "gemini"
    chain = router._resolve_chain("hello", task_type="complex_reasoning", channel_id=None)
    assert chain[0] == GEMINI_FLASH


def test_resolve_chain_forced_anthropic_leads():
    router = ModelRouter()
    router._forced_provider = "anthropic"
    chain = router._resolve_chain("hello", task_type="general", channel_id=None)
    assert chain[0] == CLAUDE_SONNET


def test_resolve_chain_forced_openai_leads():
    router = ModelRouter()
    router._forced_provider = "openai"
    chain = router._resolve_chain("hello", task_type="summarization", channel_id=None)
    assert chain[0] == GPT4O_MINI


def test_resolve_chain_forced_deepseek_leads():
    router = ModelRouter()
    router._forced_provider = "deepseek"
    chain = router._resolve_chain("code", task_type="general", channel_id=None)
    assert chain[0] == DEEPSEEK_CODER


def test_resolve_chain_forced_ollama_leads():
    router = ModelRouter()
    router._forced_provider = "ollama"
    chain = router._resolve_chain("hi", task_type="complex_reasoning", channel_id=None)
    assert chain[0] == OLLAMA_DEFAULT


def test_resolve_chain_forced_overrides_task_routing():
    """Even complex_reasoning tasks should start with the forced provider."""
    router = ModelRouter()
    router._forced_provider = "gemini"
    chain = router._resolve_chain("long complex prompt", task_type="complex_reasoning", channel_id=None)
    # Without forced_provider, complex_reasoning would lead with CLAUDE_OPUS.
    # With the override, GEMINI_FLASH must come first.
    assert chain[0] == GEMINI_FLASH


def test_resolve_chain_no_forced_provider_uses_task_routing():
    """Without _forced_provider, routing should fall through to the normal table."""
    router = ModelRouter()
    router._forced_provider = None
    # privacy_mode off, auto_complexity off so task_type is used directly
    router.auto_complexity = False
    chain = router._resolve_chain("x", task_type="cheap_inference", channel_id=None)
    # cheap_inference routes to OLLAMA_DEFAULT first
    assert chain[0] == OLLAMA_DEFAULT


def test_resolve_chain_channel_override_beats_forced_provider():
    """Per-channel overrides still take priority over _forced_provider."""
    router = ModelRouter(channel_overrides={"mybot": "specific-model"})
    router._forced_provider = "gemini"
    chain = router._resolve_chain("hi", task_type="general", channel_id="mybot")
    assert chain[0] == "specific-model"


def test_resolve_chain_privacy_mode_beats_forced_provider():
    """Privacy mode (route to Ollama) has higher priority than _forced_provider."""
    router = ModelRouter(privacy_mode=True)
    router._forced_provider = "anthropic"
    chain = router._resolve_chain("hi", task_type="general", channel_id=None)
    assert chain == [OLLAMA_DEFAULT]


# ---------------------------------------------------------------------------
# _PROVIDER_TO_MODEL mapping completeness
# ---------------------------------------------------------------------------


def test_provider_to_model_covers_all_ui_providers():
    # Original 5 providers must still be present; new providers expand the map
    core = {"gemini", "anthropic", "openai", "deepseek", "ollama"}
    assert core.issubset(set(_PROVIDER_TO_MODEL.keys()))


def test_provider_to_model_values_are_non_empty_strings():
    for provider, model in _PROVIDER_TO_MODEL.items():
        assert isinstance(model, str) and model, f"empty model for provider={provider!r}"
