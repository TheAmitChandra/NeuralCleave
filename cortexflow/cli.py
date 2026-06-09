"""CortexFlow CLI — `cortex` command entry point.

Commands:
    cortex start             Start the gateway + channels
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
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

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
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start the WebSocket gateway and all configured channel adapters."""
    from cortexflow.config import load_config
    from cortexflow.gateway.main import run

    cfg = load_config(ctx.obj.get("config_path"))
    console.print(
        f"[bold green]Starting CortexFlow v2[/bold green] on "
        f"[cyan]{cfg.gateway.bind}:{cfg.gateway.port}[/cyan]"
    )
    run(cfg)


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


def _channel_status(channels_cfg: object | None, name: str) -> str:
    if channels_cfg is None:
        return "unknown"
    enabled = getattr(channels_cfg, f"{name}_enabled", None)
    if enabled is None:
        return "not configured"
    return "enabled" if enabled else "disabled"


def _channel_detail(channels_cfg: object | None, name: str, fallback: str) -> str:
    if channels_cfg is None:
        return fallback
    detail = getattr(channels_cfg, f"{name}_detail", None)
    return detail if detail else fallback


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


@memory_group.command("search")
@click.argument("query")
@click.option("--session", "-s", default=None, help="Session ID to search within (omit to search all).")
@click.option("--limit", "-n", default=20, show_default=True, help="Maximum results to return.")
@click.pass_context
def memory_search(ctx: click.Context, query: str, session: str | None, limit: int) -> None:
    """Full-text search in long-term SQLite memory.

    QUERY is the text to search for (partial matches supported).
    """
    from cortexflow.config import load_config
    from cortexflow.memory.long_term import LongTermMemory

    cfg = load_config(ctx.obj.get("config_path"))
    lt = LongTermMemory(db_path=cfg.memory.sqlite_path)

    async def _run() -> None:
        if session:
            rows = await lt.search(session_id=session, query=query, limit=limit)
        else:
            # No session filter — search across all sessions by using a wildcard
            rows = await lt.search(session_id="%", query=query, limit=limit)

        if not rows:
            console.print(f"[dim]No results for[/dim] {query!r}")
            return

        table = Table(title=f"Memory Search: {query!r}")
        table.add_column("ID", justify="right")
        table.add_column("Session")
        table.add_column("Type")
        table.add_column("Importance", justify="right")
        table.add_column("Content")

        for row in rows:
            content_preview = str(row["content"])[:80] + ("…" if len(str(row["content"])) > 80 else "")
            table.add_row(
                str(row["id"]),
                row["session_id"],
                row["memory_type"],
                f"{row['importance_score']:.2f}",
                content_preview,
            )

        console.print(table)

    asyncio.run(_run())


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
