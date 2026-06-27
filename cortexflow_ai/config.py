"""TOML-based configuration management for CortexFlow v2.

Config file location: ~/.cortexflow/config.toml

Minimal working config (3 lines):
    [agent]
    [channels.telegram]
    bot_token = "ENV:TELEGRAM_BOT_TOKEN"
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path.home() / ".cortexflow" / "config.toml"


@dataclass
class AgentConfig:
    name: str = "My Assistant"
    model: str = "auto"


@dataclass
class ModelsConfig:
    primary: str = "claude-opus-4-8"
    fallback: str = "gemini-2.0-flash"
    fast: str = "gemini-2.0-flash"
    local: str = "ollama/llama3.2"
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    deepseek_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"


@dataclass
class MemoryConfig:
    short_term_ttl: int = 3600
    long_term_days: int = 90
    redis_url: str = "redis://localhost:6379"
    qdrant_url: str = "http://localhost:6333"
    sqlite_path: str = "~/.cortexflow/memory.db"


@dataclass
class VoiceConfig:
    stt: str = "whisper"
    tts: str = "kokoro"
    tts_voice: str = "Rachel"
    stt_model: str = "base"
    stt_device: str = "cpu"
    tts_engine: str = "kokoro"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""


@dataclass
class GatewayConfig:
    port: int = 7432
    bind: str = "127.0.0.1"


@dataclass
class UIConfig:
    web_port: int = 3000


@dataclass
class ChannelConfig:
    enabled: bool = False
    extra: dict[str, Any] = field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.extra.get(key, default)


@dataclass
class CortexFlowConfig:
    agent: AgentConfig = field(default_factory=AgentConfig)
    models: ModelsConfig = field(default_factory=ModelsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    channels: dict[str, ChannelConfig] = field(default_factory=dict)


def resolve_secret(value: str) -> str:
    """Resolve ENV:VAR_NAME references to actual environment variable values."""
    if isinstance(value, str) and value.startswith("ENV:"):
        return os.getenv(value[4:], "")
    return value


def load_config(path: Path | str | None = None) -> CortexFlowConfig:
    """Load CortexFlow config from a TOML file.

    Falls back to an all-defaults config if the file does not exist.
    """
    config_path = Path(path) if path else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return CortexFlowConfig()

    try:
        import tomllib  # Python 3.11+
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError as exc:
            raise RuntimeError(
                "tomllib (Python 3.11+) or tomli package required to load config"
            ) from exc

    with open(config_path, "rb") as f:
        raw: dict[str, Any] = tomllib.load(f)

    return _parse_config(raw)


def _parse_config(raw: dict[str, Any]) -> CortexFlowConfig:
    cfg = CortexFlowConfig()

    if agent := raw.get("agent"):
        cfg.agent = AgentConfig(
            name=agent.get("name", "My Assistant"),
            model=agent.get("model", "auto"),
        )

    if models := raw.get("models"):
        cfg.models = ModelsConfig(
            primary=models.get("primary", "claude-opus-4-8"),
            fallback=models.get("fallback", "gemini-2.0-flash"),
            fast=models.get("fast", "gemini-2.0-flash"),
            local=models.get("local", "ollama/llama3.2"),
            anthropic_api_key=resolve_secret(models.get("anthropic_api_key", "")),
            gemini_api_key=resolve_secret(models.get("gemini_api_key", "")),
            deepseek_api_key=resolve_secret(models.get("deepseek_api_key", "")),
            ollama_base_url=models.get("ollama_base_url", "http://localhost:11434"),
        )

    if memory := raw.get("memory"):
        cfg.memory = MemoryConfig(
            short_term_ttl=int(memory.get("short_term_ttl", 3600)),
            long_term_days=int(memory.get("long_term_days", 90)),
            redis_url=memory.get("redis_url", "redis://localhost:6379"),
            qdrant_url=memory.get("qdrant_url", "http://localhost:6333"),
            sqlite_path=memory.get("sqlite_path", "~/.cortexflow/memory.db"),
        )

    if voice := raw.get("voice"):
        cfg.voice = VoiceConfig(
            stt=voice.get("stt", "whisper"),
            tts=voice.get("tts", "kokoro"),
            tts_voice=voice.get("tts_voice", "Rachel"),
            stt_model=voice.get("stt_model", "base"),
            stt_device=voice.get("stt_device", "cpu"),
            tts_engine=voice.get("tts_engine", "kokoro"),
            elevenlabs_api_key=resolve_secret(voice.get("elevenlabs_api_key", "")),
            elevenlabs_voice_id=voice.get("elevenlabs_voice_id", ""),
        )

    if gateway := raw.get("gateway"):
        cfg.gateway = GatewayConfig(
            port=int(gateway.get("port", 7432)),
            bind=gateway.get("bind", "127.0.0.1"),
        )

    if ui := raw.get("ui"):
        cfg.ui = UIConfig(web_port=int(ui.get("web_port", 3000)))

    for ch_name, ch_raw in raw.get("channels", {}).items():
        if isinstance(ch_raw, dict):
            ch_copy = dict(ch_raw)
            enabled = bool(ch_copy.pop("enabled", False))
            cfg.channels[ch_name] = ChannelConfig(enabled=enabled, extra=ch_copy)

    return cfg
