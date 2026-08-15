"""Convert an OpenClaw ``openclaw.json`` config into a NeuralCleave ``config.toml``.

OpenClaw (a competing personal-AI-assistant gateway) stores its config as
JSON5 at ``~/.openclaw/openclaw.json``, with secrets optionally split out
into a companion ``.env`` file. This module targets OpenClaw's own
documented precedence — ``.env`` overrides the JSON's ``env.vars`` block —
and converts what maps cleanly onto NeuralCleave's schema:

- Provider API key references (most of OpenClaw's own standard env var
  names — ``ANTHROPIC_API_KEY``, ``OPENAI_API_KEY``, etc. — are identical
  to the ones NeuralCleave already resolves via ``ENV:VAR``)
- The primary model's provider preference (best-effort — NeuralCleave
  routes per task type rather than pinning one model, so this only seeds
  a sensible starting point)
- Telegram, Discord, and Slack bot tokens (the channels with a
  straightforward single-token 1:1 mapping)

Everything else in openclaw.json (message formatting, session policy,
per-group rules, the other ~25 channel types, ...) has no clean equivalent
in NeuralCleave's schema and is reported as skipped rather than guessed at
— see ``MigrationResult.skipped_channels``.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# OpenClaw env var name -> NeuralCleave config.toml [models] field.
# Most of these names are identical between the two projects already.
_PROVIDER_ENV_MAP: dict[str, str] = {
    "ANTHROPIC_API_KEY": "anthropic_api_key",
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "GOOGLE_API_KEY": "gemini_api_key",
    "DEEPSEEK_API_KEY": "deepseek_api_key",
    "OPENROUTER_API_KEY": "openrouter_api_key",
    "MISTRAL_API_KEY": "mistral_api_key",
    "XAI_API_KEY": "xai_api_key",
    "COHERE_API_KEY": "cohere_api_key",
    "MOONSHOT_API_KEY": "moonshot_api_key",
    "ZHIPUAI_API_KEY": "zhipuai_api_key",
    "DASHSCOPE_API_KEY": "dashscope_api_key",
    "QIANFAN_API_KEY": "qianfan_api_key",
    "ARK_API_KEY": "ark_api_key",
    "AZURE_OPENAI_API_KEY": "azure_api_key",
}

# OpenClaw agents.defaults.model.primary provider prefix (e.g. the
# "anthropic" in "anthropic/claude-sonnet-4-6") -> a NeuralCleave model id.
# NeuralCleave routes by task type rather than one pinned model, so this
# only seeds [models].primary as a starting point.
_PROVIDER_TO_PRIMARY_MODEL: dict[str, str] = {
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-4o",
    "google": "gemini-2.5-pro",
    "gemini": "gemini-2.5-pro",
    "deepseek": "deepseek-coder",
    "openrouter": "openrouter/openai/gpt-4o-mini",
    "mistral": "mistral-large-latest",
    "xai": "grok-3",
    "cohere": "command-r-plus",
    "ollama": "ollama/llama3.2:1b",
}

# OpenClaw channel name -> the openclaw.json field holding its bot token.
# Only channels with a single straightforward token field are supported;
# everything else is reported via MigrationResult.skipped_channels.
_SUPPORTED_CHANNELS: dict[str, str] = {
    "telegram": "botToken",
    "discord": "token",
    "slack": "botToken",
}


@dataclass
class MigrationResult:
    """What the importer produced, and what it could not handle."""

    toml_text: str
    migrated_providers: list[str] = field(default_factory=list)
    migrated_channels: list[str] = field(default_factory=list)
    skipped_channels: list[str] = field(default_factory=list)
    primary_model: str | None = None


# Matches an unquoted object key immediately after "{" or "," — the style
# every OpenClaw documentation example uses (agents:, channels:, botToken:, ...).
_UNQUOTED_KEY_RE = re.compile(r'([{,]\s*)([A-Za-z_$][\w$]*)\s*:')


def _json5_to_json(text: str) -> str:
    """Best-effort JSON5 -> JSON conversion.

    Handles the three JSON5 features OpenClaw's own docs and example
    configs consistently use: ``//`` line comments, unquoted object keys,
    and trailing commas before ``}``/``]``. Not a full JSON5 parser — block
    comments and single-quoted strings are not handled.
    """
    no_comments = re.sub(r"(?m)//.*$", "", text)
    quoted_keys = _UNQUOTED_KEY_RE.sub(r'\1"\2":', no_comments)
    return re.sub(r",(\s*[}\]])", r"\1", quoted_keys)


def parse_openclaw_config(text: str) -> dict[str, Any]:
    """Parse an ``openclaw.json`` file's contents, tolerating common JSON5 style."""
    return json.loads(_json5_to_json(text))


def parse_dotenv(text: str) -> dict[str, str]:
    """Parse a simple ``KEY=value`` ``.env`` file. Ignores blank lines and ``#`` comments."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            result[key] = value
    return result


def migrate(openclaw_config: dict[str, Any], env_vars: dict[str, str] | None = None) -> MigrationResult:
    """Convert a parsed ``openclaw.json`` dict (plus optional env vars) into a config.toml.

    Args:
        openclaw_config: Parsed contents of openclaw.json.
        env_vars: Environment variables to check for provider keys, merged
            on top of openclaw_config's own ``env.vars`` block — matching
            OpenClaw's own documented precedence (.env overrides the JSON
            env block).
    """
    merged_env: dict[str, Any] = dict((openclaw_config.get("env") or {}).get("vars") or {})
    merged_env.update(env_vars or {})

    lines: list[str] = ["[agent]", 'name = "My Assistant"', ""]

    # --- Provider API keys ---
    migrated_providers: list[str] = []
    model_lines: list[str] = []
    for env_name, nc_field in _PROVIDER_ENV_MAP.items():
        if env_name in merged_env:
            model_lines.append(f'{nc_field} = "ENV:{env_name}"')
            migrated_providers.append(env_name)

    # --- Primary model / provider preference ---
    primary_model: str | None = None
    primary_raw = (openclaw_config.get("agents") or {}).get("defaults", {}).get("model", {}).get("primary")
    if isinstance(primary_raw, str) and "/" in primary_raw:
        provider_prefix = primary_raw.split("/", 1)[0].lower()
        mapped = _PROVIDER_TO_PRIMARY_MODEL.get(provider_prefix)
        if mapped:
            primary_model = mapped
            model_lines.insert(0, f'primary = "{mapped}"')

    if model_lines:
        lines.append("[models]")
        lines.extend(model_lines)
        lines.append("")

    # --- Channels ---
    migrated_channels: list[str] = []
    skipped_channels: list[str] = []
    for name, chan_cfg in (openclaw_config.get("channels") or {}).items():
        if not isinstance(chan_cfg, dict):
            skipped_channels.append(name)
            continue
        token_field = _SUPPORTED_CHANNELS.get(name)
        token = chan_cfg.get(token_field) if token_field else None
        if token:
            lines.append(f"[channels.{name}]")
            lines.append("enabled = true")
            lines.append(f'bot_token = "{token}"')
            lines.append("")
            migrated_channels.append(name)
        else:
            skipped_channels.append(name)

    toml_text = "\n".join(lines).rstrip() + "\n"
    return MigrationResult(
        toml_text=toml_text,
        migrated_providers=migrated_providers,
        migrated_channels=migrated_channels,
        skipped_channels=skipped_channels,
        primary_model=primary_model,
    )


def migrate_file(config_path: Path | str, env_path: Path | str | None = None) -> MigrationResult:
    """Read and migrate an ``openclaw.json`` file (and optional ``.env``) from disk.

    If *env_path* is omitted, a sibling ``.env`` next to *config_path* is
    used automatically when present, matching OpenClaw's own documented
    local-run layout.
    """
    config_file = Path(config_path).expanduser()
    parsed = parse_openclaw_config(config_file.read_text(encoding="utf-8"))

    if env_path is not None:
        env_file: Path | None = Path(env_path).expanduser()
    else:
        candidate = config_file.parent / ".env"
        env_file = candidate if candidate.exists() else None

    env_vars: dict[str, str] = {}
    if env_file is not None and env_file.exists():
        env_vars = parse_dotenv(env_file.read_text(encoding="utf-8"))

    return migrate(parsed, env_vars=env_vars)
