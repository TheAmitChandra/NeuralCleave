"""Unit tests for NeuralCleave.config."""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from neuralcleave.config import (
    NeuralCleaveConfig,
    GatewayConfig,
    UIConfig,
    _parse_config,
    load_config,
    resolve_secret,
)

# ---------------------------------------------------------------------------
# resolve_secret
# ---------------------------------------------------------------------------


def test_resolve_secret_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MY_TOKEN", "abc123")
    assert resolve_secret("ENV:MY_TOKEN") == "abc123"


def test_resolve_secret_missing_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NONEXISTENT_VAR", raising=False)
    assert resolve_secret("ENV:NONEXISTENT_VAR") == ""


def test_resolve_secret_plain_value() -> None:
    assert resolve_secret("plain-value") == "plain-value"


def test_resolve_secret_non_string() -> None:
    # resolve_secret is typed to accept str; passing non-str returns as-is
    assert resolve_secret(42) == 42  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# load_config — file not found → defaults
# ---------------------------------------------------------------------------


def test_load_config_no_file_returns_defaults(tmp_path: Path) -> None:
    cfg = load_config(tmp_path / "nonexistent.toml")
    assert isinstance(cfg, NeuralCleaveConfig)
    assert cfg.gateway.port == 7432
    assert cfg.gateway.bind == "127.0.0.1"
    assert cfg.agent.name == "My Assistant"


# ---------------------------------------------------------------------------
# _parse_config — inline TOML dicts
# ---------------------------------------------------------------------------


def test_parse_agent_section() -> None:
    cfg = _parse_config({"agent": {"name": "TestBot", "model": "claude-opus-4-8"}})
    assert cfg.agent.name == "TestBot"
    assert cfg.agent.model == "claude-opus-4-8"


def test_parse_gateway_section() -> None:
    cfg = _parse_config({"gateway": {"port": 8080, "bind": "0.0.0.0"}})
    assert cfg.gateway.port == 8080
    assert cfg.gateway.bind == "0.0.0.0"


def test_parse_memory_section() -> None:
    cfg = _parse_config({"memory": {"short_term_ttl": 7200, "long_term_days": 30}})
    assert cfg.memory.short_term_ttl == 7200
    assert cfg.memory.long_term_days == 30


def test_parse_voice_section() -> None:
    cfg = _parse_config({"voice": {"stt": "whisper", "tts": "elevenlabs", "tts_voice": "Rachel"}})
    assert cfg.voice.tts == "elevenlabs"
    assert cfg.voice.stt == "whisper"


def test_parse_models_section_api_keys() -> None:
    cfg = _parse_config({
        "models": {
            "anthropic_api_key": "sk-direct",
            "ollama_base_url": "http://example:1234",
        }
    })
    assert cfg.models.anthropic_api_key == "sk-direct"
    assert cfg.models.ollama_base_url == "http://example:1234"


def test_parse_models_section_resolves_env_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    cfg = _parse_config({"models": {"anthropic_api_key": "ENV:ANTHROPIC_API_KEY"}})
    assert cfg.models.anthropic_api_key == "sk-from-env"


def test_models_section_defaults() -> None:
    cfg = _parse_config({})
    assert cfg.models.anthropic_api_key == ""
    assert cfg.models.openai_api_key == ""
    assert cfg.models.ollama_base_url == "http://localhost:11434"


def test_parse_models_section_openai_api_key() -> None:
    cfg = _parse_config({"models": {"openai_api_key": "sk-openai-direct"}})
    assert cfg.models.openai_api_key == "sk-openai-direct"


def test_parse_models_section_resolves_openai_env_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-from-env")
    cfg = _parse_config({"models": {"openai_api_key": "ENV:OPENAI_API_KEY"}})
    assert cfg.models.openai_api_key == "sk-openai-from-env"


def test_parse_memory_section_connection_urls() -> None:
    cfg = _parse_config({
        "memory": {
            "redis_url": "redis://example:6380",
            "qdrant_url": "http://example:6333",
            "sqlite_path": "/tmp/custom.db",
        }
    })
    assert cfg.memory.redis_url == "redis://example:6380"
    assert cfg.memory.qdrant_url == "http://example:6333"
    assert cfg.memory.sqlite_path == "/tmp/custom.db"


def test_memory_section_defaults() -> None:
    cfg = _parse_config({})
    assert cfg.memory.redis_url == "redis://localhost:6379"
    assert cfg.memory.sqlite_path == "~/.neuralcleave/memory.db"


def test_parse_voice_section_stt_tts_engine_fields() -> None:
    cfg = _parse_config({
        "voice": {
            "stt_model": "small",
            "stt_device": "cuda",
            "tts_engine": "elevenlabs",
            "elevenlabs_api_key": "ENV:ELEVENLABS_API_KEY",
        }
    })
    assert cfg.voice.stt_model == "small"
    assert cfg.voice.stt_device == "cuda"
    assert cfg.voice.tts_engine == "elevenlabs"


def test_voice_section_defaults() -> None:
    cfg = _parse_config({})
    assert cfg.voice.stt == "none"
    assert cfg.voice.tts == "none"
    assert cfg.voice.tts_engine == "none"
    assert cfg.voice.stt_model == "base"
    assert cfg.voice.stt_device == "cpu"
    assert cfg.voice.elevenlabs_voice_id == ""


def test_parse_voice_section_elevenlabs_voice_id() -> None:
    cfg = _parse_config({"voice": {"elevenlabs_voice_id": "cloned-voice-abc123"}})
    assert cfg.voice.elevenlabs_voice_id == "cloned-voice-abc123"


def test_parse_channel_enabled() -> None:
    cfg = _parse_config({
        "channels": {
            "telegram": {"enabled": True, "bot_token": "tok123"},
        }
    })
    assert "telegram" in cfg.channels
    assert cfg.channels["telegram"].enabled is True
    assert cfg.channels["telegram"].get("bot_token") == "tok123"


def test_parse_channel_disabled_by_default() -> None:
    cfg = _parse_config({"channels": {"discord": {"bot_token": "dt"}}})
    assert cfg.channels["discord"].enabled is False


def test_parse_empty_dict_uses_all_defaults() -> None:
    cfg = _parse_config({})
    assert cfg.gateway == GatewayConfig()
    assert cfg.channels == {}


def test_parse_config_ui_section() -> None:
    cfg = _parse_config({"ui": {"web_port": 4321}})
    assert cfg.ui == UIConfig(web_port=4321)


# ---------------------------------------------------------------------------
# load_config — from a real TOML file
# ---------------------------------------------------------------------------


def test_load_config_from_file(tmp_path: Path) -> None:
    toml_content = textwrap.dedent("""\
        [agent]
        name = "MyBot"

        [gateway]
        port = 9999
        bind = "0.0.0.0"

        [channels.telegram]
        enabled = true
        bot_token = "tok"
    """)
    config_file = tmp_path / "config.toml"
    config_file.write_text(toml_content, encoding="utf-8")

    cfg = load_config(config_file)
    assert cfg.agent.name == "MyBot"
    assert cfg.gateway.port == 9999
    assert cfg.channels["telegram"].enabled is True


# ---------------------------------------------------------------------------
# load_config — tomllib/tomli fallback chain
# ---------------------------------------------------------------------------


def test_load_config_falls_back_to_tomli_when_tomllib_missing(tmp_path: Path) -> None:
    import builtins
    import sys
    import types

    real_import = builtins.__import__
    fake_tomli = types.ModuleType("tomli")
    fake_tomli.load = lambda f: {"agent": {"name": "ViaTomli"}}  # type: ignore[attr-defined]

    def fake_import(name, *args, **kwargs):
        if name == "tomllib":
            raise ImportError("no tomllib")
        return real_import(name, *args, **kwargs)

    config_file = tmp_path / "config.toml"
    config_file.write_text("[agent]\nname = \"ignored\"\n", encoding="utf-8")

    with patch.dict(sys.modules, {"tomli": fake_tomli}):
        with patch("builtins.__import__", side_effect=fake_import):
            cfg = load_config(config_file)

    assert cfg.agent.name == "ViaTomli"


def test_load_config_raises_when_neither_tomllib_nor_tomli_available(tmp_path: Path) -> None:
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("tomllib", "tomli"):
            raise ImportError(f"no {name}")
        return real_import(name, *args, **kwargs)

    config_file = tmp_path / "config.toml"
    config_file.write_text("[agent]\nname = \"x\"\n", encoding="utf-8")

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="tomllib"):
            load_config(config_file)
