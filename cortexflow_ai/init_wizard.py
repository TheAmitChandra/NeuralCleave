"""Guided first-run setup wizard for CortexFlow v2.

Invoked by `cortex init`. Collects user preferences interactively and
writes ~/.cortexflow/config.toml plus the workspace scaffold files
(SOUL.md, RULES.md, TOOLS.md, MEMORY.md).

The public surface is intentionally small so that callers and tests can
exercise the pure logic without needing a live terminal:

    answers = WizardAnswers(agent_name="Hal", channels=["telegram"])
    toml = build_config_toml(answers)
    write_wizard_output(answers, config_dir=Path("/tmp/test"))
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MODEL_MAP: dict[str, str] = {
    "1": "claude-opus-4-8",
    "2": "gemini-2.5-flash",
    "3": "ollama/llama3.2",
}

_MODEL_LABELS: dict[str, str] = {
    "1": "Claude Opus  (best quality — needs ANTHROPIC_API_KEY)",
    "2": "Gemini Flash (fast, free tier — needs GEMINI_API_KEY)",
    "3": "Ollama       (local, fully private — no API key needed)",
}

_CHANNEL_ENV: dict[str, str] = {
    "telegram": "TELEGRAM_BOT_TOKEN",
    "discord": "DISCORD_BOT_TOKEN",
    "slack": "SLACK_BOT_TOKEN",
    "whatsapp": "WHATSAPP_SESSION_PATH",
    "email": "EMAIL_USER",
}

_VOICE_STT_CHOICES = ("whisper", "none")
_VOICE_TTS_CHOICES = ("elevenlabs", "kokoro", "system", "none")

_DEFAULT_SOUL = """\
You are a helpful, thoughtful personal AI assistant.
Respond concisely and clearly. Ask for clarification when you are unsure.
Remember the user's preferences and adapt your communication style over time.
"""

_DEFAULT_RULES = """\
# Rules
- Never fabricate facts — say "I don't know" when uncertain.
- Always confirm before taking irreversible actions (deleting files, sending emails).
- Keep responses concise unless the user asks for detail.
- Do not reveal system instructions or workspace file contents unless asked.
"""

_DEFAULT_TOOLS = """\
# Available Tools
- web_search: Search the web for current information
- file_ops: Read and write local files (within allowed paths)
"""

_DEFAULT_MEMORY = """\
# Memory Instructions
- Remember user preferences, recurring tasks, and important facts.
- Ignore trivial filler and small-talk.
- Prioritise work-related and goal-oriented memories.
- Forget information the user explicitly asks you to forget.
"""


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class WizardAnswers:
    """Captures every choice the wizard collects."""

    agent_name: str = "My Assistant"
    primary_model: str = "gemini-2.5-flash"
    channels: list[str] = field(default_factory=list)
    voice_stt: str = "whisper"
    voice_tts: str = "kokoro"
    short_term_ttl: int = 3600
    long_term_days: int = 90


# ---------------------------------------------------------------------------
# Pure config-generation helpers (no I/O — fully testable)
# ---------------------------------------------------------------------------


def build_config_toml(answers: WizardAnswers) -> str:
    """Return the TOML text for config.toml from wizard answers.

    Pure function — no file I/O, no side effects.
    """
    lines: list[str] = [
        "[agent]",
        f'name = "{answers.agent_name}"',
        'model = "auto"',
        "",
        "[models]",
        f'primary = "{answers.primary_model}"',
        'fallback = "gemini-2.5-flash"',
        'fast    = "gemini-2.5-flash"',
        'local   = "ollama/llama3.2"',
        "",
        "[memory]",
        f"short_term_ttl = {answers.short_term_ttl}",
        f"long_term_days = {answers.long_term_days}",
        "",
        "[voice]",
        f'stt = "{answers.voice_stt}"',
        f'tts = "{answers.voice_tts}"',
        "",
        "[gateway]",
        "port = 7432",
        'bind = "127.0.0.1"',
        "",
        "[ui]",
        "web_port = 3000",
        "",
    ]

    for ch in answers.channels:
        env_var = _CHANNEL_ENV.get(ch, f"{ch.upper()}_TOKEN")
        lines += [
            f"[channels.{ch}]",
            "enabled = true",
            f'bot_token = "ENV:{env_var}"',
            "",
        ]

    return "\n".join(lines)


def _workspace_files() -> dict[str, str]:
    """Return mapping of workspace filename → default content."""
    return {
        "SOUL.md": _DEFAULT_SOUL,
        "RULES.md": _DEFAULT_RULES,
        "TOOLS.md": _DEFAULT_TOOLS,
        "MEMORY.md": _DEFAULT_MEMORY,
    }


def write_wizard_output(
    answers: WizardAnswers,
    config_dir: Path,
    force: bool = False,
) -> Path:
    """Write config.toml and workspace scaffold to *config_dir*.

    Returns the path of the written config file.
    Does not overwrite existing workspace files unless *force* is True.
    """
    config_dir.mkdir(parents=True, exist_ok=True)
    workspace = config_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    cfg_file = config_dir / "config.toml"
    cfg_file.write_text(build_config_toml(answers), encoding="utf-8")

    for filename, content in _workspace_files().items():
        dest = workspace / filename
        if not dest.exists() or force:
            dest.write_text(content, encoding="utf-8")

    return cfg_file


# ---------------------------------------------------------------------------
# Interactive wizard (calls click — tested via CliRunner)
# ---------------------------------------------------------------------------


def run_wizard(
    config_dir: Path | None = None,
    force: bool = False,
) -> Path:
    """Run the interactive first-run wizard.

    Prompts the user, then delegates to *write_wizard_output*.
    Returns the path of the written config file.
    """
    import click

    cfg_dir = config_dir or (Path.home() / ".cortexflow")
    cfg_file = cfg_dir / "config.toml"

    if cfg_file.exists() and not force:
        click.echo(
            click.style(f"Config already exists at {cfg_file}", fg="yellow")
            + " — use --force to overwrite."
        )
        return cfg_file

    click.echo(click.style("\n  CortexFlow v2 — First-run Setup\n", bold=True))

    # ── Agent name ────────────────────────────────────────────────────────
    agent_name: str = click.prompt("  Agent name", default="My Assistant")

    # ── Primary model ─────────────────────────────────────────────────────
    click.echo("\n  Choose your primary LLM:")
    for key, label in _MODEL_LABELS.items():
        click.echo(f"    {key}) {label}")
    model_key: str = click.prompt(
        "  Choice",
        type=click.Choice(list(_MODEL_MAP.keys())),
        default="2",
    )
    primary_model = _MODEL_MAP[model_key]

    # ── Channels ──────────────────────────────────────────────────────────
    click.echo("\n  Enable channels (y/n):")
    channels: list[str] = []
    for ch in _CHANNEL_ENV:
        if click.confirm(f"    {ch.capitalize()}?", default=False):
            channels.append(ch)

    # ── Voice ─────────────────────────────────────────────────────────────
    click.echo("\n  Voice settings:")
    voice_stt: str = click.prompt(
        "  STT engine",
        type=click.Choice(list(_VOICE_STT_CHOICES)),
        default="whisper",
    )
    voice_tts: str = click.prompt(
        "  TTS engine",
        type=click.Choice(list(_VOICE_TTS_CHOICES)),
        default="kokoro",
    )

    answers = WizardAnswers(
        agent_name=agent_name,
        primary_model=primary_model,
        channels=channels,
        voice_stt=voice_stt,
        voice_tts=voice_tts,
    )

    cfg_path = write_wizard_output(answers, cfg_dir, force=force)

    click.echo(click.style(f"\n  Setup complete! Config written to {cfg_path}", fg="green"))
    click.echo(f"  Workspace files created at {cfg_dir / 'workspace'}/\n")
    click.echo("  Next steps:")
    click.echo("    1. Export API keys as environment variables (see ENV: entries in config).")
    click.echo("    2. Run: cortex start\n")

    return cfg_path
