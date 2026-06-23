"""CortexFlow CLI — `cortex` command entry point.

Commands:
    cortex start             Start the gateway + channels
    cortex start --background  Start the gateway as a detached process
    cortex stop              Stop a background gateway started above
    cortex chat              Interactive chat session in the terminal
    cortex config show       Print the resolved config
    cortex config init       Write a starter config.toml to ~/.cortexflow/
    cortex channels list     List configured channel adapters and status
    cortex memory prune      Remove low-importance long-term memories
    cortex memory search     Full-text search in long-term SQLite memory
    cortex tools list        List all registered tools with descriptions
    cortex version           Print version
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

from cortexflow.config import DEFAULT_CONFIG_PATH

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
def init_cmd(force: bool, config_dir: str | None) -> None:
    """Run the guided first-run setup wizard."""
    from pathlib import Path

    from cortexflow.init_wizard import run_wizard

    run_wizard(
        config_dir=Path(config_dir) if config_dir else None,
        force=force,
    )


# ---------------------------------------------------------------------------
# start
# ---------------------------------------------------------------------------


@cli.command()
@click.option(
    "--background", "-b", is_flag=True, default=False,
    help="Start the gateway as a detached background process and return immediately.",
)
@click.pass_context
def start(ctx: click.Context, background: bool) -> None:
    """Start the WebSocket gateway and all configured channel adapters."""
    from cortexflow.config import load_config

    config_path = ctx.obj.get("config_path")
    cfg = load_config(config_path)

    if background:
        pidfile = _pidfile_path(config_path)
        existing_pid = _read_pidfile(pidfile)
        if existing_pid is not None and _is_process_running(existing_pid):
            console.print(f"[yellow]CortexFlow is already running[/yellow] (PID {existing_pid})")
            return

        cmd = [sys.executable, "-m", "cortexflow.cli"]
        if config_path:
            cmd += ["-c", str(config_path)]
        cmd.append("start")

        pid = _spawn_background(cmd)
        pidfile.parent.mkdir(parents=True, exist_ok=True)
        pidfile.write_text(str(pid), encoding="utf-8")
        console.print(f"[bold green]Starting CortexFlow v2 in background[/bold green] (PID {pid})")
        return

    from cortexflow.gateway.main import run

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
    from cortexflow.config import load_config
    from cortexflow.models.router import ModelRouter

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

    from cortexflow.config import load_config

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
frontend_port = 3000
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
    from cortexflow.config import load_config

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
    from cortexflow.tools.registry import ToolRegistry

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
    from cortexflow.config import load_config
    from cortexflow.memory.retrieval import MemoryRetrievalPipeline

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
    from cortexflow.config import load_config
    from cortexflow.memory.long_term import LongTermMemory

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


@memory_group.command("archive")
@click.option("--session", "-s", default=None, help="Archive a specific session ID immediately.")
@click.option("--days", "-d", default=30, show_default=True, help="Archive sessions inactive for more than this many days.")
@click.pass_context
def memory_archive(ctx: click.Context, session: str | None, days: int) -> None:
    """Condense inactive sessions' memory into one searchable archive summary."""
    from cortexflow.config import load_config
    from cortexflow.memory.archiver import SessionArchiver
    from cortexflow.memory.long_term import LongTermMemory
    from cortexflow.models.router import ModelRouter

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
    from cortexflow.config import load_config
    from cortexflow.memory.long_term import LongTermMemory

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
    from cortexflow.config import load_config

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
    from cortexflow import __version__

    console.print(f"CortexFlow [bold]{__version__}[/bold]")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    cli(obj={})


if __name__ == "__main__":
    main()
