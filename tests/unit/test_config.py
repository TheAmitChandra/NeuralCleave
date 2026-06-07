"""Unit tests for cortexflow.config."""

from __future__ import annotations

import os
import textwrap
import tempfile
from pathlib import Path

import pytest

from cortexflow.config import (
    CortexFlowConfig,
    GatewayConfig,
    load_config,
    resolve_secret,
    _parse_config,
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
    assert isinstance(cfg, CortexFlowConfig)
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
