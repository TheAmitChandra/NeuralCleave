"""AgentRuntime — the top-level orchestrator that wires everything together.

Responsibilities:
- Register channel adapters from config
- Route inbound messages from any channel to the CognitivePipeline
- Handle built-in slash commands (/reset, /memory, /status, /compact)
- Send the pipeline's response back via the originating adapter
- Manage session GC (idle session cleanup)
- Expose runtime metrics (message count, active sessions, errors)

Usage::

    runtime = AgentRuntime.from_config(cfg)
    await runtime.start()
    # ... gateway is running ...
    await runtime.stop()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from cortexflow.channels.base import ChannelAdapter, InboundMessage
from cortexflow.agent.session import SessionManager
from cortexflow.agent.pipeline import CognitivePipeline, PipelineResult
from cortexflow.config import CortexFlowConfig
from cortexflow.memory.retrieval import MemoryRetrievalPipeline
from cortexflow.models.router import ModelRouter
from cortexflow.workspace import WorkspaceFiles, WorkspaceLoader

logger = logging.getLogger(__name__)

# Slash commands handled by the runtime (not the LLM)
_SLASH_COMMANDS = {"/reset", "/memory", "/status", "/compact", "/help"}


@dataclass
class RuntimeMetrics:
    """Running counters updated as messages are processed."""

    messages_received: int = 0
    messages_sent: int = 0
    errors: int = 0
    pipeline_latency_ms_total: float = 0.0
    started_at: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        if self.messages_received == 0:
            return 0.0
        return self.pipeline_latency_ms_total / self.messages_received

    @property
    def uptime_seconds(self) -> float:
        return time.time() - self.started_at


class AgentRuntime:
    """Top-level runtime that connects channels, sessions, and the pipeline.

    Args:
        pipeline:       The cognitive pipeline (intent → generate).
        session_mgr:    Session manager (creates/retrieves sessions).
        adapters:       Registered channel adapters.
        gc_interval:    Seconds between idle session cleanup. Default 300.
    """

    def __init__(
        self,
        pipeline: CognitivePipeline,
        session_mgr: SessionManager,
        adapters: list[ChannelAdapter] | None = None,
        gc_interval: float = 300.0,
    ) -> None:
        self._pipeline = pipeline
        self._sessions = session_mgr
        self._adapters: dict[str, ChannelAdapter] = {}
        self._gc_interval = gc_interval
        self._gc_task: asyncio.Task | None = None  # type: ignore[type-arg]
        self.metrics = RuntimeMetrics()

        for adapter in (adapters or []):
            self.register_adapter(adapter)

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_config(cls, cfg: CortexFlowConfig) -> "AgentRuntime":
        """Build a fully-wired AgentRuntime from a CortexFlowConfig."""
        router = ModelRouter(
            anthropic_api_key=getattr(cfg.models, "anthropic_api_key", None),
            gemini_api_key=getattr(cfg.models, "gemini_api_key", None),
            deepseek_api_key=getattr(cfg.models, "deepseek_api_key", None),
            ollama_base_url=getattr(cfg.models, "ollama_base_url", "http://localhost:11434"),
        )
        memory = MemoryRetrievalPipeline(
            redis_url=cfg.memory.redis_url,
            qdrant_url=cfg.memory.qdrant_url,
            sqlite_path=cfg.memory.sqlite_path,
        )
        loader = WorkspaceLoader()
        workspace_files = loader.get()

        pipeline = CognitivePipeline(
            router=router,
            memory=memory,
            workspace=workspace_files,
            agent_name=cfg.agent.name,
        )
        session_mgr = SessionManager()

        adapters = _build_adapters(cfg)
        return cls(pipeline=pipeline, session_mgr=session_mgr, adapters=adapters)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        adapter.on_message(self._on_message)
        self._adapters[adapter.channel_id] = adapter

    async def start(self) -> None:
        """Connect all registered adapters and start the GC loop."""
        for channel_id, adapter in self._adapters.items():
            try:
                await adapter.connect()
                logger.info("runtime: channel %s connected", channel_id)
            except Exception as exc:
                logger.error("runtime: channel %s failed to connect: %s", channel_id, exc)

        self._gc_task = asyncio.create_task(self._gc_loop())
        logger.info(
            "AgentRuntime started — %d channel(s) active", len(self._adapters)
        )

    async def stop(self) -> None:
        """Disconnect all adapters and cancel the GC loop."""
        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass

        for adapter in self._adapters.values():
            try:
                await adapter.disconnect()
            except Exception as exc:
                logger.warning("runtime: adapter %s disconnect error: %s", adapter.channel_id, exc)

        logger.info("AgentRuntime stopped")

    # ------------------------------------------------------------------
    # Message dispatch
    # ------------------------------------------------------------------

    async def _on_message(self, msg: InboundMessage) -> None:
        self.metrics.messages_received += 1
        text = (msg.text or "").strip()

        # Handle built-in slash commands
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd in _SLASH_COMMANDS:
                await self._handle_command(cmd, msg)
                return

        # Normal message → cognitive pipeline
        session = self._sessions.get_or_create(msg.channel, msg.sender_id)
        try:
            result: PipelineResult = await self._pipeline.run(msg, session)
            await self._send_reply(msg, result.response)
            self.metrics.pipeline_latency_ms_total += result.latency_ms
            self.metrics.messages_sent += 1
            logger.info(
                "runtime: %s/%s → %s (%.0fms)",
                msg.channel, msg.sender_id[:8], result.model, result.latency_ms,
            )
        except Exception as exc:
            self.metrics.errors += 1
            logger.error("runtime: pipeline error for %s/%s: %s", msg.channel, msg.sender_id, exc)
            await self._send_reply(msg, "Sorry, something went wrong. Please try again.")

    async def _send_reply(self, original: InboundMessage, text: str) -> None:
        adapter = self._adapters.get(original.channel)
        if not adapter:
            logger.warning("runtime: no adapter for channel %s", original.channel)
            return
        await adapter.send(original.sender_id, text, reply_to=original.reply_to_id)

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    async def _handle_command(self, cmd: str, msg: InboundMessage) -> None:
        session = self._sessions.get_or_create(msg.channel, msg.sender_id)

        if cmd == "/reset":
            session.clear()
            reply = "Session reset. Starting fresh."

        elif cmd == "/memory":
            ctx = await self._pipeline._memory.retrieve(
                "recent context", top_k=5, include_semantic=False
            )
            if ctx.results:
                lines = [f"- {r.content}" for r in ctx.results[:5]]
                reply = "Recent memory:\n" + "\n".join(lines)
            else:
                reply = "No memory entries found for this session."

        elif cmd == "/status":
            reply = (
                f"CortexFlow Status\n"
                f"Uptime: {self.metrics.uptime_seconds:.0f}s\n"
                f"Active sessions: {self._sessions.active_count}\n"
                f"Messages handled: {self.metrics.messages_received}\n"
                f"Avg latency: {self.metrics.avg_latency_ms:.0f}ms\n"
                f"Errors: {self.metrics.errors}"
            )

        elif cmd == "/compact":
            if session.turn_count < 4:
                reply = "Not enough history to compact yet."
            else:
                summary_prompt = (
                    "Summarise this conversation in 3-5 bullet points, preserving key facts:\n\n"
                    + session.build_prompt()
                )
                try:
                    gen = await self._pipeline._router.generate(
                        summary_prompt, task_type="summarization", max_tokens=300
                    )
                    session.clear()
                    session.add_turn("system", f"Conversation summary:\n{gen.text.strip()}")
                    reply = f"Conversation compacted. Summary:\n{gen.text.strip()}"
                except Exception as exc:
                    reply = f"Compact failed: {exc}"

        else:  # /help
            reply = (
                "Commands:\n"
                "/reset   — Clear conversation history\n"
                "/memory  — Show recent memory\n"
                "/status  — Runtime statistics\n"
                "/compact — Summarize and compress history\n"
                "/help    — Show this message"
            )

        await self._send_reply(msg, reply)

    # ------------------------------------------------------------------
    # GC loop
    # ------------------------------------------------------------------

    async def _gc_loop(self) -> None:
        while True:
            await asyncio.sleep(self._gc_interval)
            removed = self._sessions.gc()
            if removed:
                logger.debug("runtime: GC removed %d idle sessions", removed)


def _build_adapters(cfg: CortexFlowConfig) -> list[ChannelAdapter]:
    """Instantiate adapters for all enabled channels in config."""
    adapters: list[ChannelAdapter] = []
    for name, ch_cfg in cfg.channels.items():
        if not ch_cfg.enabled:
            continue
        adapter = _make_adapter(name, ch_cfg.extra)
        if adapter:
            adapters.append(adapter)
    return adapters


def _make_adapter(name: str, config: dict[str, Any]) -> ChannelAdapter | None:
    try:
        if name == "telegram":
            from cortexflow.channels.telegram import TelegramAdapter
            return TelegramAdapter(config)
        if name == "discord":
            from cortexflow.channels.discord_ import DiscordAdapter
            return DiscordAdapter(config)
        if name == "slack":
            from cortexflow.channels.slack import SlackAdapter
            return SlackAdapter(config)
        if name == "whatsapp":
            from cortexflow.channels.whatsapp import WhatsAppAdapter
            return WhatsAppAdapter(config)
        if name == "email":
            from cortexflow.channels.email_ import EmailAdapter
            return EmailAdapter(config)
    except Exception as exc:
        logger.warning("runtime: could not load adapter %s: %s", name, exc)
    logger.debug("runtime: unknown channel %s — skipping", name)
    return None
