"""CortexFlow CLI — `cortex` command entry point.

Commands:
    cortex start               Start the gateway + channels
    cortex start --background  Start the gateway as a detached process
    cortex stop                Stop a background gateway started above
    cortex open                Open the web UI in the default browser
    cortex tray                Start backend in background and open the web UI
    cortex chat                Interactive chat session in the terminal
    cortex config show         Print the resolved config
    cortex config init         Write a starter config.toml to ~/.cortexflow/
    cortex channels list       List configured channel adapters and status
    cortex memory prune        Remove low-importance long-term memories
    cortex memory edit         Edit a memory entry's content/importance
    cortex memory search       Full-text search in long-term SQLite memory
    cortex tools list          List all registered tools with descriptions
    cortex plugins list        List all registered plugins and their load status
    cortex plugins reload      Hot-reload all plugins without gateway restart
    cortex plugins reload NAME Hot-reload a single plugin by name
    cortex voice listen        Always-on continuous voice mode (no wake word)
    cortex autostart enable    Register CortexFlow to start at login
    cortex autostart disable   Remove the autostart entry
    cortex autostart status    Show whether autostart is registered
    cortex cloud check         Verify Docker + Compose are installed
    cortex cloud generate      Write Dockerfile, docker-compose.yml, railway.toml, render.yaml
    cortex cloud status        Show detected cloud platform and env vars
    cortex version             Print version
    cortex update              Check PyPI and self-update if a newer version exists
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from cortexflow_ai.config import DEFAULT_CONFIG_PATH

console = Console()


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.option("--config", "-c", default=None, help="Path to config.toml")
@click.pass_context
def cli(ctx: click.Context, config: str | None) -> None:
    """CortexFlow — Personal AI Assistant Gateway."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config


# ---------------------------------------------------------------------------
# init  (guided first-run wizard)
# ---------------------------------------------------------------------------


@cli.command("init")
@click.option("--force", is_flag=True, default=False, help="Overwrite existing config.")
@click.option("--dir", "config_dir", default=None, help="Target config directory.")
@click.option(
    "--non-interactive", "-y", "non_interactive", is_flag=True, default=False,
    help="Skip prompts and write default config (suitable for scripted installs).",
)
def init_cmd(force: bool, config_dir: str | None, non_interactive: bool) -> None:
    """Run the guided first-run setup wizard.

    Pass --non-interactive (-y) to skip all prompts and write sensible
    defaults immediately — useful for one-liner install scripts.
    """
    from pathlib import Path

    from cortexflow_ai.init_wizard import run_wizard

    run_wizard(
        config_dir=Path(config_dir) if config_dir else None,
        force=force,
        non_interactive=non_interactive,
    )


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--background", "-b", is_flag=True, default=False,
    help="Start the gateway as a detached background process and return immediately.",
)
@click.option("--bind", default=None, help="Override the gateway bind address from config.")
@click.option("--port", default=None, type=int, help="Override the gateway port from config.")
@click.pass_context
def start(ctx: click.Context, background: bool, bind: str | None, port: int | None) -> None:
    """Start the WebSocket gateway and all configured channel adapters."""
    from cortexflow_ai.config import load_config

    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)
    if bind:
        cfg.gateway.bind = bind
    if port:
        cfg.gateway.port = port

    if background:
        pidfile = _pidfile_path(config_path)
        existing_pid = _read_pidfile(pidfile)
        if existing_pid is not None and _is_process_running(existing_pid):
            console.print(f"[yellow]CortexFlow is already running[/yellow] (PID {existing_pid})")
            return

        cmd = [sys.executable, "-m", "cortexflow_ai.cli"]
        if config_path:
            cmd += ["-c", str(config_path)]
        cmd.append("start")
        if bind:
            cmd += ["--bind", bind]
        if port:
            cmd += ["--port", str(port)]

        pid = _spawn_background(cmd)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(pid), encoding="utf-8")
        console.print(f"[bold green]Starting CortexFlow v2 in background[/bold green] (PID {pid})")
        return

    from cortexflow_ai.gateway.main import run

    console.print(
        f"[bold green]Starting CortexFlow v2[/bold green] on "
        f"[cyan]{cfg.gateway.bind}:{cfg.gateway.port}[/cyan]"
    )
    run(cfg)


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def stop(ctx: click.Context) -> None:
    """Stop a background gateway started with `cortex start --background`."""
    pidfile = _pidfile_path(ctx.obj.get("config_path"))
    pid = _read_pidfile(pidfile)

    if pid is None:
        if pidfile.exists():
            pidfile.unlink(missing_ok=True)
            console.print("[red]Corrupt PID file removed.[/red]")
        else:
            console.print("[yellow]No background CortexFlow process is tracked.[/yellow]")
        return

    if not _is_process_running(pid):
        pidfile.unlink(missing_ok=True)
        console.print(f"[yellow]Process {pid} was not running.[/yellow] Cleaned up stale PID file.")
        return

    _terminate_process(pid)
    pidfile.unlink(missing_ok=True)
    console.print(f"[green]Stopped CortexFlow[/green] (PID {pid})")


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------


@cli.command("open")
@click.option("--bind", default=None, help="Override the UI bind address from config.")
@click.option("--port", default=None, type=int, help="Override the UI port from config.")
@click.pass_context
def open_cmd(ctx: click.Context, bind: str | None, port: int | None) -> None:
    """Open the CortexFlow web UI in the default browser."""
    import webbrowser

    from cortexflow_ai.config import load_config

    cfg = load_config(ctx.obj.get("config_path"))
    ui_host = bind or "localhost"
    ui_port = port or cfg.ui.web_port
    url = f"http://{ui_host}:{ui_port}"
    console.print(f"[bold green]Opening CortexFlow UI[/bold green] at [cyan]{url}[/cyan]")
    webbrowser.open(url)


# ---------------------------------------------------------------------------
# tray  (start backend in background + open web UI in browser)
# ---------------------------------------------------------------------------


@cli.command("tray")
@click.option("--bind", default=None, help="Override the gateway bind address from config.")
@click.option("--port", default=None, type=int, help="Override the gateway port from config.")
@click.option("--ui-port", "ui_port", default=None, type=int, help="Override the web UI port from config.")
@click.pass_context
def tray(ctx: click.Context, bind: str | None, port: int | None, ui_port: int | None) -> None:
    """Start the backend in background and open the web UI — one command, zero terminals."""
    import time
    import webbrowser

    from cortexflow_ai.config import load_config

    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)
    if bind:
        cfg.gateway.bind = bind
    if port:
        cfg.gateway.port = port

    pidfile = _pidfile_path(config_path)
    existing_pid = _read_pidfile(pidfile)
    if existing_pid is not None and _is_process_running(existing_pid):
        console.print(f"[yellow]Backend already running[/yellow] (PID {existing_pid})")
    else:
        cmd = [sys.executable, "-m", "cortexflow_ai.cli"]
        if config_path:
            cmd += ["-c", str(config_path)]
        cmd.append("start")
        if bind:
            cmd += ["--bind", bind]
        if port:
            cmd += ["--port", str(port)]

        pid = _spawn_background(cmd)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(pid), encoding="utf-8")
        console.print(f"[bold green]Backend started[/bold green] (PID {pid})")
        time.sleep(1)

    effective_ui_port = ui_port or cfg.ui.web_port
    url = f"http://localhost:{effective_ui_port}"
    console.print(f"[bold green]Opening UI[/bold green] at [cyan]{url}[/cyan]")
    webbrowser.open(url)


def _pidfile_path(config_path: str | None) -> Path:
    base = Path(config_path).expanduser().parent if config_path else DEFAULT_CONFIG_PATH.parent
    return base / "cortex.pid"


def _read_pidfile(pidfile: Path) -> int | None:
    if not pidfile.exists():
        return None
    try:
        return int(pidfile.read_text(encoding="utf-8").strip())
    except ValueError:
        return None


def _is_process_running(pid: int) -> bool:
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True
        )
        return str(pid) in result.stdout
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_process(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True)
    else:
        import signal

        os.kill(pid, signal.SIGTERM)


def _spawn_background(cmd: list[str]) -> int:
    """Launch *cmd* as a detached background process. Returns its PID."""
    kwargs: dict[str, Any] = {}
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs
    )
    return proc.pid


# ---------------------------------------------------------------------------
# chat
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def chat(ctx: click.Context) -> None:
    """Interactive terminal chat session."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.models.router import ModelRouter

    cfg = load_config(ctx.obj.get("config_path"))
    router = ModelRouter(
        anthropic_api_key=cfg.models.anthropic_api_key,
        gemini_api_key=cfg.models.gemini_api_key,
    )

    console.print("[bold]CortexFlow Chat[/bold] — type [italic]exit[/italic] to quit")

    async def _loop() -> None:
        while True:
            try:
                user_input = click.prompt("\nYou", prompt_suffix=" > ")
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Goodbye.[/dim]")
                break
            if user_input.strip().lower() in {"exit", "quit", "bye"}:
                console.print("[dim]Goodbye.[/dim]")
                break
            with console.status("[dim]Thinking…[/dim]"):
                result = await router.generate(user_input, task_type="general")
            console.print(f"\n[bold cyan]CortexFlow[/bold cyan]: {result.text}")
            console.print(f"[dim]({result.model})[/dim]")

    asyncio.run(_loop())


# ---------------------------------------------------------------------------
# config group
# ---------------------------------------------------------------------------


@cli.group("config")
def config_group() -> None:
    """Manage CortexFlow configuration."""


@config_group.command("show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Print the resolved configuration."""
    import dataclasses
    import json

    from cortexflow_ai.config import load_config

    cfg = load_config(ctx.obj.get("config_path"))
    data = dataclasses.asdict(cfg)
    console.print_json(json.dumps(data))


@config_group.command("init")
def config_init() -> None:
    """Write a starter config.toml to ~/.cortexflow/config.toml."""
    target = Path.home() / ".cortexflow" / "config.toml"
    if target.exists():
        console.print(f"[yellow]Config already exists at {target}[/yellow]")
        return

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        """\
[agent]
name = "CortexFlow"
persona = "You are CortexFlow, a helpful personal AI assistant."
timezone = "UTC"
language = "en"

[models]
anthropic_api_key = "ENV:ANTHROPIC_API_KEY"
gemini_api_key    = "ENV:GEMINI_API_KEY"
deepseek_api_key  = "ENV:DEEPSEEK_API_KEY"
ollama_base_url   = "http://localhost:11434"

[memory]
redis_url    = "redis://localhost:6379"
qdrant_url   = "http://localhost:6333"
sqlite_path  = "~/.cortexflow/memory.db"

[voice]
stt_model   = "base"
stt_device  = "cpu"
tts_engine  = "elevenlabs"
elevenlabs_api_key = "ENV:ELEVENLABS_API_KEY"

[gateway]
bind = "127.0.0.1"
port = 7432

[ui]
web_port = 3000
""",
        encoding="utf-8",
    )
    console.print(f"[green]Created config at[/green] {target}")


@config_group.command("edit")
@click.pass_context
def config_edit(ctx: click.Context) -> None:
    """Open config.toml in $EDITOR, creating it first if missing."""
    config_path = Path(ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH)
    if not config_path.exists():
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("[agent]\nname = \"My Assistant\"\n", encoding="utf-8")
        console.print(f"[green]Created config at[/green] {config_path}")
    click.edit(filename=str(config_path))


# ---------------------------------------------------------------------------
# channels group
# ---------------------------------------------------------------------------


@cli.group("channels")
def channels_group() -> None:
    """Inspect channel adapter status."""


@channels_group.command("list")
@click.pass_context
def channels_list(ctx: click.Context) -> None:
    """List all configured channel adapters and their status."""
    from cortexflow_ai.config import load_config

    cfg = load_config(ctx.obj.get("config_path"))

    table = Table(title="Channel Adapters")
    table.add_column("Channel", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    ch = cfg.channels if hasattr(cfg, "channels") else None

    rows = [
        ("terminal", "built-in", "Always available via `cortex chat`"),
        ("websocket", "built-in", f"ws://{cfg.gateway.bind}:{cfg.gateway.port}"),
        ("telegram", _channel_status(ch, "telegram"), _channel_detail(ch, "telegram", "Set TELEGRAM_BOT_TOKEN")),
        ("slack", _channel_status(ch, "slack"), _channel_detail(ch, "slack", "Set SLACK_BOT_TOKEN")),
        ("discord", _channel_status(ch, "discord"), _channel_detail(ch, "discord", "Set DISCORD_BOT_TOKEN")),
        ("voice", _channel_status(ch, "voice"), f"STT={cfg.voice.stt_model} TTS={cfg.voice.tts_engine}"),
    ]
    for name, status, detail in rows:
        colour = "green" if status in ("built-in", "enabled") else "dim"
        table.add_row(name, f"[{colour}]{status}[/{colour}]", detail)

    console.print(table)


@channels_group.command("add")
@click.argument("name")
@click.pass_context
def channels_add(ctx: click.Context, name: str) -> None:
    """Enable a channel adapter (writes `enabled = true` to config.toml)."""
    config_path = Path(ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH)
    _set_channel_enabled(config_path, name, enabled=True)
    console.print(f"[green]Enabled[/green] channel '{name}' in {config_path}")


@channels_group.command("remove")
@click.argument("name")
@click.pass_context
def channels_remove(ctx: click.Context, name: str) -> None:
    """Disable a channel adapter (writes `enabled = false` to config.toml)."""
    config_path = Path(ctx.obj.get("config_path") or DEFAULT_CONFIG_PATH)
    _set_channel_enabled(config_path, name, enabled=False)
    console.print(f"[yellow]Disabled[/yellow] channel '{name}' in {config_path}")


def _channel_status(channels_cfg: dict[str, object] | None, name: str) -> str:
    if not channels_cfg or name not in channels_cfg:
        return "not configured"
    return "enabled" if channels_cfg[name].enabled else "disabled"  # type: ignore[attr-defined]


def _channel_detail(channels_cfg: dict[str, object] | None, name: str, fallback: str) -> str:
    if not channels_cfg or name not in channels_cfg:
        return fallback
    extra = channels_cfg[name].extra  # type: ignore[attr-defined]
    if not extra:
        return fallback
    parts = []
    for key, value in extra.items():
        if any(s in key.lower() for s in ("token", "key", "secret", "password")):
            parts.append(f"{key}=***")
        else:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else fallback


def _set_channel_enabled(config_path: Path, name: str, *, enabled: bool) -> None:
    """Toggle `enabled = true|false` inside a `[channels.<name>]` TOML section.

    Appends the section if it doesn't exist yet. Uses plain text editing
    rather than a TOML writer dependency, since the config schema here is
    flat key/value pairs.
    """
    if not config_path.exists():
        raise click.ClickException(
            f"No config file at {config_path}. Run `cortex config init` first."
        )

    header = f"[channels.{name}]"
    value_line = f"enabled = {'true' if enabled else 'false'}"
    lines = config_path.read_text(encoding="utf-8").splitlines()

    section_start = next((i for i, ln in enumerate(lines) if ln.strip() == header), None)

    if section_start is None:
        lines += ["", header, value_line]
    else:
        section_end = next(
            (i for i in range(section_start + 1, len(lines)) if lines[i].strip().startswith("[")),
            len(lines),
        )
        enabled_idx = next(
            (i for i in range(section_start + 1, section_end) if lines[i].strip().startswith("enabled")),
            None,
        )
        if enabled_idx is not None:
            lines[enabled_idx] = value_line
        else:
            lines.insert(section_start + 1, value_line)

    config_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# tools group
# ---------------------------------------------------------------------------


@cli.group("tools")
def tools_group() -> None:
    """Inspect and manage registered agent tools."""


@tools_group.command("list")
def tools_list() -> None:
    """List all registered built-in tools with name, permissions, and description."""
    from cortexflow_ai.tools.registry import ToolRegistry

    registry = ToolRegistry.default()

    table = Table(title="Registered Tools")
    table.add_column("Name", style="bold cyan")
    table.add_column("Permissions")
    table.add_column("Description")

    for name in registry.names:
        tool = registry.get(name)
        if tool is None:
            continue
        perms = ", ".join(tool.permissions) if tool.permissions else "[dim]none[/dim]"
        table.add_row(name, perms, tool.description)

    console.print(table)


# ---------------------------------------------------------------------------
# voice group
# ---------------------------------------------------------------------------


@cli.group("voice")
def voice_group() -> None:
    """Manage TTS voices."""


@voice_group.command("listen")
@click.option("--model", "-m", default="base", show_default=True,
              help="Whisper model size: tiny|base|small|medium|large-v3.")
@click.option("--threshold-rms", default=300.0, show_default=True,
              help="RMS energy threshold for speech detection.")
@click.option("--silence-s", default=0.8, show_default=True,
              help="Seconds of silence to end an utterance.")
@click.option("--min-speech-s", default=0.2, show_default=True,
              help="Minimum speech duration to transcribe (shorter = discarded).")
@click.option("--max-speech-s", default=30.0, show_default=True,
              help="Maximum single utterance duration before force-end.")
@click.option("--device", default="cpu", show_default=True,
              help="Whisper inference device: cpu or cuda.")
@click.option("--language", default=None,
              help="Force language (e.g. 'en'). Omit for auto-detect.")
def voice_listen(
    model: str,
    threshold_rms: float,
    silence_s: float,
    min_speech_s: float,
    max_speech_s: float,
    device: str,
    language: str | None,
) -> None:
    """Start continuous voice listening — no wake word required.

    \b
    Captures microphone audio continuously, uses energy-based VAD to detect
    when you're speaking, then transcribes each utterance with Whisper and
    prints it. Press Ctrl+C to stop.

    \b
    Requirements:
        pip install sounddevice numpy faster-whisper
    """
    from cortexflow_ai.voice.continuous import ContinuousVoiceListener
    from cortexflow_ai.voice.stt import WhisperSTT

    stt = WhisperSTT(model_size=model, device=device, language=language)
    listener = ContinuousVoiceListener(
        stt,
        silence_threshold_rms=threshold_rms,
        silence_duration_s=silence_s,
        min_speech_duration_s=min_speech_s,
        max_speech_duration_s=max_speech_s,
    )

    def on_transcription(text: str) -> None:
        console.print(f"[bold cyan]You:[/bold cyan] {text}")

    listener.on_transcription(on_transcription)
    console.print(
        "[bold green]Continuous voice mode active[/bold green] "
        f"(model={model}, threshold={threshold_rms:.0f}rms, "
        f"silence={silence_s}s) — speak freely. "
        "Press [bold]Ctrl+C[/bold] to stop."
    )

    async def _run() -> None:
        await listener.start()
        try:
            while listener.is_listening:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            pass
        finally:
            await listener.stop()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


@voice_group.command("clone")
@click.argument("name")
@click.argument("audio_files", nargs=-1, required=True, type=click.Path(exists=True, dir_okay=False))
@click.option("--description", "-d", default=None, help="Optional description for the new voice.")
@click.pass_context
def voice_clone(ctx: click.Context, name: str, audio_files: tuple[str, ...], description: str | None) -> None:
    """Clone a custom ElevenLabs voice from one or more audio sample files."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.voice.tts import TTSEngine

    cfg = load_config(ctx.obj.get("config_path"))
    tts = TTSEngine(elevenlabs_api_key=cfg.voice.elevenlabs_api_key)

    samples = [Path(f).read_bytes() for f in audio_files]

    async def _run() -> None:
        voice_id = await tts.clone_voice(name, samples, description=description)
        console.print(f"[green]Cloned voice[/green] '{name}' -> voice_id [bold]{voice_id}[/bold]")
        console.print(
            f"Add [cyan]tts_engine = \"elevenlabs\"[/cyan] and "
            f"[cyan]elevenlabs_voice_id = \"{voice_id}\"[/cyan] under [voice] in config.toml to use it."
        )

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# memory group
# ---------------------------------------------------------------------------


@cli.group("memory")
def memory_group() -> None:
    """Manage the 3-tier memory system."""


@memory_group.command("prune")
@click.option("--threshold", "-t", default=0.2, show_default=True, help="Importance threshold below which entries are removed.")
@click.pass_context
def memory_prune(ctx: click.Context, threshold: float) -> None:
    """Remove low-importance entries from SQLite + Qdrant near-duplicates."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.memory.retrieval import MemoryRetrievalPipeline

    cfg = load_config(ctx.obj.get("config_path"))
    pipeline = MemoryRetrievalPipeline(
        redis_url=cfg.memory.redis_url,
        qdrant_url=cfg.memory.qdrant_url,
        sqlite_path=cfg.memory.sqlite_path,
    )

    async def _run() -> None:
        result = await pipeline.prune_low_importance(importance_threshold=threshold)
        table = Table(title="Memory Prune Results")
        table.add_column("Stat")
        table.add_column("Count", justify="right")
        table.add_row("SQLite rows pruned", str(result["pruned"]))
        table.add_row("Qdrant duplicates removed", str(result["deduplicated"]))
        console.print(table)

    asyncio.run(_run())


@memory_group.command("clear")
@click.option("--session", "-s", default=None, help="Limit clearing to a single session ID (omit to clear all).")
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip the confirmation prompt.")
@click.pass_context
def memory_clear(ctx: click.Context, session: str | None, yes: bool) -> None:
    """Permanently delete long-term memory entries."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.memory.long_term import LongTermMemory

    target = f"session '{session}'" if session else "ALL sessions"
    if not yes and not click.confirm(f"This will permanently delete memory for {target}. Continue?"):
        console.print("[dim]Aborted.[/dim]")
        return

    cfg = load_config(ctx.obj.get("config_path"))
    lt = LongTermMemory(db_path=cfg.memory.sqlite_path)

    async def _run() -> None:
        removed = await lt.clear_all(session_id=session)
        plural = "entry" if removed == 1 else "entries"
        console.print(f"[green]Cleared {removed} memory {plural}[/green] for {target}")

    asyncio.run(_run())


@memory_group.command("edit")
@click.argument("entry_id", type=int)
@click.option("--content", "-c", default=None, help="New content text for the entry.")
@click.option("--importance", "-i", type=float, default=None, help="New importance score (0.0-1.0).")
@click.pass_context
def memory_edit(ctx: click.Context, entry_id: int, content: str | None, importance: float | None) -> None:
    """Edit an existing memory entry's content and/or importance score."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.memory.long_term import LongTermMemory

    if content is None and importance is None:
        raise click.ClickException("Provide --content and/or --importance")

    cfg = load_config(ctx.obj.get("config_path"))
    lt = LongTermMemory(db_path=cfg.memory.sqlite_path)

    async def _run() -> None:
        found = False
        if content is not None:
            found = await lt.update_content(entry_id, content) or found
        if importance is not None:
            found = await lt.update_importance(entry_id, importance) or found

        if not found:
            console.print(f"[yellow]No memory entry found with id {entry_id}[/yellow]")
            return
        console.print(f"[green]Updated memory entry[/green] {entry_id}")

    asyncio.run(_run())


@memory_group.command("archive")
@click.option("--session", "-s", default=None, help="Archive a specific session ID immediately.")
@click.option("--days", "-d", default=30, show_default=True, help="Archive sessions inactive for more than this many days.")
@click.pass_context
def memory_archive(ctx: click.Context, session: str | None, days: int) -> None:
    """Condense inactive sessions' memory into one searchable archive summary."""
    from cortexflow_ai.config import load_config
    from cortexflow_ai.memory.archiver import SessionArchiver
    from cortexflow_ai.memory.long_term import LongTermMemory
    from cortexflow_ai.models.router import ModelRouter

    cfg = load_config(ctx.obj.get("config_path"))
    lt = LongTermMemory(db_path=cfg.memory.sqlite_path)
    router = ModelRouter(
        anthropic_api_key=cfg.models.anthropic_api_key,
        gemini_api_key=cfg.models.gemini_api_key,
        deepseek_api_key=cfg.models.deepseek_api_key,
        ollama_base_url=cfg.models.ollama_base_url,
    )
    archiver = SessionArchiver(long_term=lt, router=router)

    async def _run() -> None:
        await lt.init_schema()
        if session:
            summary = await archiver.archive_session(session)
            if summary is None:
                console.print(f"[yellow]Nothing to archive for session[/yellow] '{session}'")
            else:
                console.print(f"[green]Archived session[/green] '{session}'")
        else:
            archived = await archiver.archive_inactive_sessions(older_than_days=days)
            if not archived:
                console.print(f"[dim]No sessions inactive for more than {days} day(s).[/dim]")
            else:
                console.print(f"[green]Archived {len(archived)} session(s)[/green]: {', '.join(archived)}")

    asyncio.run(_run())


@memory_group.command("search")
@click.argument("query")
@click.option("--session", "-s", default=None, help="Session ID to search within (omit to search all).")
@click.option("--tag", "-t", default=None, help="Filter to entries whose tags contain this value, instead of a content search.")
@click.option("--limit", "-n", default=20, show_default=True, help="Maximum results to return.")
@click.pass_context
def memory_search(ctx: click.Context, query: str, session: str | None, tag: str | None, limit: int) -> None:
    """Full-text search in long-term SQLite memory.

    QUERY is the text to search for (partial matches supported), unless
    --tag is given, in which case QUERY is ignored and entries are
    filtered by tag instead.
    """
    from cortexflow_ai.config import load_config
    from cortexflow_ai.memory.long_term import LongTermMemory

    cfg = load_config(ctx.obj.get("config_path"))
    lt = LongTermMemory(db_path=cfg.memory.sqlite_path)

    async def _run() -> None:
        if tag:
            rows = await lt.search_by_tag(session_id=session, tag=tag, limit=limit)
        else:
            rows = await lt.search(session_id=session, query=query, limit=limit)

        if not rows:
            target_desc = tag if tag else query
            console.print(f"[dim]No results for[/dim] {target_desc!r}")
            return

        title = f"Memory Tag: {tag!r}" if tag else f"Memory Search: {query!r}"
        table = Table(title=title)
        table.add_column("ID", justify="right")
        table.add_column("Session")
        table.add_column("Type")
        table.add_column("Tags")
        table.add_column("Importance", justify="right")
        table.add_column("Content")

        for row in rows:
            content_preview = str(row["content"])[:80] + ("…" if len(str(row["content"])) > 80 else "")
            table.add_row(
                str(row["id"]),
                row["session_id"],
                row["memory_type"],
                row.get("tags", "") or "[dim]none[/dim]",
                f"{row['importance_score']:.2f}",
                content_preview,
            )

        console.print(table)

    asyncio.run(_run())


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show agent config, enabled channels, and memory stats at a glance."""
    from cortexflow_ai.config import load_config

    cfg = load_config(ctx.obj.get("config_path"))

    table = Table(title="CortexFlow Status")
    table.add_column("Setting", style="bold")
    table.add_column("Value")
    table.add_row("Agent", cfg.agent.name)
    table.add_row("Model (primary)", cfg.models.primary)
    table.add_row("Gateway", f"{cfg.gateway.bind}:{cfg.gateway.port}")
    table.add_row("Voice STT / TTS", f"{cfg.voice.stt_model} / {cfg.voice.tts_engine}")

    enabled = [name for name, ch in cfg.channels.items() if ch.enabled]
    table.add_row("Enabled channels", ", ".join(enabled) if enabled else "[dim]none[/dim]")
    table.add_row("Long-term memory rows", str(_count_memory_rows(cfg.memory.sqlite_path)))

    console.print(table)


def _count_memory_rows(sqlite_path: str) -> int | str:
    import sqlite3

    db_path = Path(sqlite_path).expanduser()
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(str(db_path)) as conn:
            row = conn.execute("SELECT COUNT(*) FROM memory_entries").fetchone()
            return row[0] if row else 0
    except sqlite3.Error:
        return "unavailable"


# ---------------------------------------------------------------------------
# version
# ---------------------------------------------------------------------------


@cli.command()
def version() -> None:
    """Print the installed CortexFlow version."""
    from cortexflow_ai import __version__

    console.print(f"CortexFlow [bold]{__version__}[/bold]")


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


@cli.command()
@click.option("--check", is_flag=True, default=False, help="Only check for updates, don't install.")
def update(check: bool) -> None:
    """Check PyPI for a newer CortexFlow version and optionally install it."""
    from cortexflow_ai import __version__
    from cortexflow_ai.update_checker import get_latest_version, is_newer

    latest = asyncio.run(get_latest_version("cortexflow-ai"))
    if latest is None:
        console.print(
            "[yellow]Could not check for updates[/yellow] (offline, or not yet published to PyPI)."
        )
        return

    if not is_newer(latest, __version__):
        console.print(f"[green]CortexFlow is up to date[/green] (v{__version__})")
        return

    console.print(f"[bold]Update available:[/bold] v{__version__} -> v{latest}")
    if check:
        console.print("Run [cyan]cortex update[/cyan] (without --check) to install it.")
        return

    import subprocess
    import sys

    console.print("[dim]Installing update…[/dim]")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "cortexflow-ai"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        console.print(f"[green]Updated to v{latest}.[/green] Restart cortex to use the new version.")
    else:
        console.print(f"[red]Update failed:[/red]\n{result.stderr}")


# ---------------------------------------------------------------------------
# plugins group
# ---------------------------------------------------------------------------


@cli.group("plugins")
def plugins_group() -> None:
    """Inspect and hot-reload installed CortexFlow plugins."""


@plugins_group.command("list")
def plugins_list() -> None:
    """List all registered plugins and their current load status."""
    from cortexflow_ai.plugins.registry import PluginRegistry
    from cortexflow_ai.tools.registry import ToolRegistry

    tool_registry = ToolRegistry.default()
    registry = PluginRegistry(tool_registry)
    registry.discover()

    table = Table(title="Registered Plugins")
    table.add_column("Name", style="bold cyan")
    table.add_column("Version")
    table.add_column("Type")
    table.add_column("Status")
    table.add_column("Description")

    plugins = registry.all_plugins
    if not plugins:
        console.print("[dim]No plugins discovered.[/dim]")
        console.print("[dim]Install a cortexflow plugin package and declare the 'cortexflow.plugins' entry point.[/dim]")
        return

    for plugin in plugins:
        status = "[green]loaded[/green]" if registry.is_loaded(plugin.metadata.name) else "[dim]discovered[/dim]"
        table.add_row(
            plugin.metadata.name,
            plugin.metadata.version,
            plugin.metadata.plugin_type,
            status,
            plugin.metadata.description,
        )

    console.print(table)


@plugins_group.command("reload")
@click.argument("name", required=False, default=None)
def plugins_reload(name: str | None) -> None:
    """Hot-reload plugins without restarting the gateway.

    NAME  Optional plugin name. Omit to reload all registered plugins.

    \b
    Examples:
        cortex plugins reload                  # reload all
        cortex plugins reload cortexflow-github # reload one
    """
    import asyncio as _asyncio

    from cortexflow_ai.plugins.registry import PluginRegistry
    from cortexflow_ai.tools.registry import ToolRegistry

    tool_registry = ToolRegistry.default()
    registry = PluginRegistry(tool_registry)
    registry.discover()

    async def _run() -> None:
        if name is None:
            total = len(registry.all_plugins)
            if total == 0:
                console.print("[dim]No plugins registered.[/dim]")
                return
            count = await registry.reload_all()
            if count == total:
                console.print(f"[green]Reloaded {count}/{total} plugin(s) successfully.[/green]")
            else:
                console.print(f"[yellow]Reloaded {count}/{total} plugin(s). Check logs for errors.[/yellow]")
        else:
            if not any(p.metadata.name == name for p in registry.all_plugins):
                console.print(f"[red]Plugin '{name}' not found.[/red] Run [cyan]cortex plugins list[/cyan] to see available plugins.")
                raise SystemExit(1)
            ok = await registry.reload_plugin(name)
            if ok:
                console.print(f"[green]Reloaded plugin '{name}' successfully.[/green]")
            else:
                console.print(f"[red]Failed to reload plugin '{name}'.[/red] Check logs for errors.")
                raise SystemExit(1)

    _asyncio.run(_run())


# ---------------------------------------------------------------------------
# cloud group
# ---------------------------------------------------------------------------


@cli.group("cloud")
def cloud_group() -> None:
    """Cloud deployment: generate manifests and check prerequisites."""


@cloud_group.command("check")
def cloud_check() -> None:
    """Check Docker pre-flight prerequisites for cloud deployment."""
    from cortexflow_ai.cloud.health import check_compose, check_docker, detect_platform

    platform = detect_platform()
    if platform:
        console.print(f"[bold green]Running in cloud:[/bold green] {platform}")
    else:
        console.print("[dim]Running locally (no cloud platform detected)[/dim]")

    docker_ok, docker_info = check_docker()
    compose_ok, compose_info = check_compose()

    table = Table(title="Prerequisites")
    table.add_column("Tool")
    table.add_column("Status")
    table.add_column("Details")
    table.add_row(
        "Docker",
        "[green]available[/green]" if docker_ok else "[red]missing[/red]",
        docker_info,
    )
    table.add_row(
        "Docker Compose",
        "[green]available[/green]" if compose_ok else "[yellow]missing[/yellow]",
        compose_info,
    )
    console.print(table)

    if not docker_ok:
        raise SystemExit(1)


@cloud_group.command("generate")
@click.option("--output-dir", "-o", default=".", help="Directory to write manifest files to.")
@click.option("--service-name", "-n", default="cortexflow", help="Container service name.")
@click.option("--port", "-p", default=7432, type=int, help="Gateway port.")
@click.option("--python-version", "-V", default="3.12", help="Python base image version (3.11/3.12/3.13).")
@click.option("--no-redis", is_flag=True, default=False, help="Omit Redis from docker-compose.yml.")
@click.option("--no-qdrant", is_flag=True, default=False, help="Omit Qdrant from docker-compose.yml.")
@click.option("--restart", default="unless-stopped", help="Docker restart policy.")
def cloud_generate(
    output_dir: str,
    service_name: str,
    port: int,
    python_version: str,
    no_redis: bool,
    no_qdrant: bool,
    restart: str,
) -> None:
    """Generate Dockerfile, docker-compose.yml, railway.toml, and render.yaml."""
    from cortexflow_ai.cloud.config import CloudDeployConfig
    from cortexflow_ai.cloud.manifests import (
        generate_compose,
        generate_dockerfile,
        generate_railway,
        generate_render,
    )

    config = CloudDeployConfig(
        port=port,
        service_name=service_name,
        python_version=python_version,
        redis_enabled=not no_redis,
        qdrant_enabled=not no_qdrant,
        restart_policy=restart,
    )

    errors = config.validate()
    if errors:
        for err in errors:
            console.print(f"[red]Error:[/red] {err}")
        raise SystemExit(1)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    files = {
        "Dockerfile": generate_dockerfile(config),
        "docker-compose.yml": generate_compose(config),
        "railway.toml": generate_railway(config),
        "render.yaml": generate_render(config),
    }
    for filename, content in files.items():
        path = out / filename
        path.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {path}")

    console.print("\n[bold]Next steps:[/bold]")
    console.print("  [cyan]docker compose up -d[/cyan]   # local Docker")
    console.print("  [cyan]railway up[/cyan]               # Railway.app")
    console.print("  [cyan]render deploy[/cyan]             # Render.com")


@cloud_group.command("status")
def cloud_status() -> None:
    """Show detected cloud platform and environment variables."""
    from cortexflow_ai.cloud.health import cloud_env_vars, detect_platform

    platform = detect_platform()

    table = Table(title="Cloud Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row(
        "Platform",
        f"[green]{platform}[/green]" if platform else "[dim]local[/dim]",
    )
    for k, v in sorted(cloud_env_vars().items()):
        table.add_row(k, v)

    console.print(table)


# ---------------------------------------------------------------------------
# autostart group
# ---------------------------------------------------------------------------


@cli.group("autostart")
def autostart_group() -> None:
    """Register or remove CortexFlow as an OS login-time autostart entry."""


@autostart_group.command("enable")
def autostart_enable() -> None:
    """Register CortexFlow to start automatically at login.

    \b
    Windows  → HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run
    macOS    → ~/Library/LaunchAgents/ai.cortexflow.plist
    Linux    → ~/.config/systemd/user/cortexflow.service
    """
    from cortexflow_ai.autostart import AutostartManager

    result = AutostartManager().enable()
    style = "yellow" if result.already_set else ("green" if result.success else "red")
    console.print(f"[{style}]{result.message}[/{style}]")
    if not result.success:
        raise SystemExit(1)


@autostart_group.command("disable")
def autostart_disable() -> None:
    """Remove the CortexFlow autostart entry."""
    from cortexflow_ai.autostart import AutostartManager

    result = AutostartManager().disable()
    style = "yellow" if result.already_set else ("green" if result.success else "red")
    console.print(f"[{style}]{result.message}[/{style}]")
    if not result.success:
        raise SystemExit(1)


@autostart_group.command("status")
def autostart_status() -> None:
    """Show whether CortexFlow autostart is currently registered."""
    from cortexflow_ai.autostart import AutostartManager

    result = AutostartManager().status()
    if result.enabled:
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[dim]{result.message}[/dim]")
    if result.entry_path:
        console.print(f"[dim]Entry path: {result.entry_path}[/dim]")


# ---------------------------------------------------------------------------
# Skills — write / list / show / delete user-defined skills
# ---------------------------------------------------------------------------


@cli.group("skills")
def skills_group() -> None:
    """Manage user-written skills (self-modifying tools)."""


@skills_group.command("write")
@click.argument("name")
@click.option("--file", "-f", "source_file", default=None, help="Path to Python file containing the skill code.")
@click.option("--code", "-c", "inline_code", default=None, help="Inline Python source code for the skill.")
@click.option("--description", "-d", default="", help="One-line description of the skill.")
def skills_write(name: str, source_file: str | None, inline_code: str | None, description: str) -> None:
    """Write a new skill from a file or inline code and load it."""
    from cortexflow_ai.skills.writer import SkillWriter

    if source_file and inline_code:
        console.print("[red]Provide either --file or --code, not both.[/red]")
        raise SystemExit(1)
    if not source_file and not inline_code:
        console.print("[red]Provide --file <path> or --code <python-source>.[/red]")
        raise SystemExit(1)

    if source_file:
        path = Path(source_file)
        if not path.exists():
            console.print(f"[red]File not found: {path}[/red]")
            raise SystemExit(1)
        code = path.read_text(encoding="utf-8")
    else:
        code = inline_code or ""

    writer = SkillWriter()
    try:
        message = writer.write_skill(name, code, description)
        console.print(f"[green]{message}[/green]")
    except (ValueError, RuntimeError) as exc:
        console.print(f"[red]Error: {exc}[/red]")
        raise SystemExit(1)


@skills_group.command("list")
def skills_list() -> None:
    """List all user-written skills."""
    from cortexflow_ai.skills.writer import SkillWriter

    writer = SkillWriter()
    skills = writer.list_skills()
    if not skills:
        console.print("[dim]No user-written skills found.[/dim]")
        return
    for info in skills:
        status = "[green]loaded[/green]" if info.loaded else "[dim]not loaded[/dim]"
        console.print(f"  {info.name}  ({status})  {info.path}")


@skills_group.command("show")
@click.argument("name")
def skills_show(name: str) -> None:
    """Show the source code of a user-written skill."""
    from cortexflow_ai.skills.writer import SkillWriter

    writer = SkillWriter()
    try:
        code = writer.get_skill_code(name)
        console.print(code)
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)


@skills_group.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt.")
def skills_delete(name: str, yes: bool) -> None:
    """Delete a user-written skill."""
    from cortexflow_ai.skills.writer import SkillWriter

    if not yes:
        click.confirm(f"Delete skill '{name}'?", abort=True)

    writer = SkillWriter()
    try:
        writer.delete_skill(name)
        console.print(f"[green]Skill '{name}' deleted.[/green]")
    except FileNotFoundError as exc:
        console.print(f"[red]{exc}[/red]")
        raise SystemExit(1)


@skills_group.command("validate")
@click.argument("file", type=click.Path(exists=True))
def skills_validate(file: str) -> None:
    """Validate a Python file as a skill (checks syntax and blocked imports)."""
    from cortexflow_ai.skills.writer import SkillWriter

    code = Path(file).read_text(encoding="utf-8")
    writer = SkillWriter()
    errors = writer.validate_code(code)
    if errors:
        for err in errors:
            console.print(f"[red]  {err}[/red]")
        raise SystemExit(1)
    console.print("[green]Skill code is valid.[/green]")


# ---------------------------------------------------------------------------
# Sandbox — manage execution backends (local / Docker / SSH)
# ---------------------------------------------------------------------------


@cli.group("sandbox")
def sandbox_group() -> None:
    """Manage sandbox execution backends (local, Docker, SSH)."""


@sandbox_group.command("status")
@click.option("--backend", "-b", default="local", show_default=True,
              type=click.Choice(["local", "docker", "ssh"]),
              help="Backend to inspect.")
@click.option("--host", default=None, help="SSH host (required for --backend=ssh).")
@click.option("--port", default=22, show_default=True, help="SSH port.")
@click.option("--username", "-u", default=None, help="SSH username.")
@click.option("--image", default="python:3.12-slim", show_default=True,
              help="Docker image (for --backend=docker).")
def sandbox_status(backend: str, host: str | None, port: int, username: str | None, image: str) -> None:
    """Show the status and configuration of a sandbox backend."""
    import asyncio

    from cortexflow_ai.sandbox.manager import SandboxManager

    if backend == "local":
        mgr = SandboxManager.local()
    elif backend == "docker":
        mgr = SandboxManager.docker(image=image)
    else:
        if not host:
            console.print("[red]--host is required for --backend=ssh[/red]")
            raise SystemExit(1)
        mgr = SandboxManager.ssh(host=host, port=port, username=username)

    info = mgr.info()
    reachable = asyncio.run(mgr.ping())

    table = Table(title=f"Sandbox Status — {backend}")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("Backend", backend)
    table.add_row("Reachable", "[green]Yes[/green]" if reachable else "[red]No[/red]")
    for k, v in sorted(info.items()):
        if k != "backend":
            table.add_row(k.replace("_", " ").title(), str(v))
    console.print(table)


@sandbox_group.command("test")
@click.option("--backend", "-b", default="local", show_default=True,
              type=click.Choice(["local", "docker", "ssh"]),
              help="Backend to test.")
@click.option("--host", default=None, help="SSH host (for --backend=ssh).")
@click.option("--port", default=22, show_default=True, help="SSH port.")
@click.option("--username", "-u", default=None, help="SSH username.")
@click.option("--image", default="python:3.12-slim", show_default=True,
              help="Docker image (for --backend=docker).")
@click.option("--command", "-c", "cmd", default="echo 'sandbox ok'",
              show_default=True, help="Command to run in the sandbox.")
def sandbox_test(backend: str, host: str | None, port: int, username: str | None,
                 image: str, cmd: str) -> None:
    """Run a test command in the specified sandbox backend."""
    import asyncio

    from cortexflow_ai.sandbox.manager import SandboxManager

    if backend == "local":
        mgr = SandboxManager.local()
    elif backend == "docker":
        mgr = SandboxManager.docker(image=image)
    else:
        if not host:
            console.print("[red]--host is required for --backend=ssh[/red]")
            raise SystemExit(1)
        mgr = SandboxManager.ssh(host=host, port=port, username=username)

    result = asyncio.run(mgr.execute(cmd))

    console.print(f"[bold]Backend:[/bold] {backend}")
    console.print(f"[bold]Exit code:[/bold] {result.exit_code}")
    if result.timed_out:
        console.print("[red]TIMED OUT[/red]")
    if result.stdout:
        console.print(f"[bold]stdout:[/bold]\n{result.stdout}")
    if result.stderr:
        console.print(f"[bold]stderr:[/bold]\n{result.stderr}")
    if not result.success:
        raise SystemExit(result.exit_code if result.exit_code != 0 else 1)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
