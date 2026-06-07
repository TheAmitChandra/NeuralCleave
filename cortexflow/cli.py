"""CortexFlow CLI — `cortex` command entry point.

Commands:
    cortex start          Start the gateway + channels
    cortex chat           Interactive chat session in the terminal
    cortex config show    Print the resolved config
    cortex config init    Write a starter config.toml to ~/.cortexflow/
    cortex memory prune   Remove low-importance long-term memories
    cortex version        Print version
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
