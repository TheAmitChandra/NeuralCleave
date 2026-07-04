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
import os
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from cortexflow_ai.agent.pipeline import (
    CognitivePipeline,
    PipelineResult,
    PipelineStreamChunk,
)
from cortexflow_ai.agent.session import SessionManager
from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage
from cortexflow_ai.config import CortexFlowConfig
from cortexflow_ai.memory.long_term import LongTermMemory
from cortexflow_ai.memory.retrieval import MemoryRetrievalPipeline
from cortexflow_ai.models.router import ModelRouter
from cortexflow_ai.observability.metrics import REGISTRY
from cortexflow_ai.workspace import WorkspaceLoader

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
        long_term: LongTermMemory | None = None,
        stt: Any | None = None,
        tts: Any | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._sessions = session_mgr
        self._adapters: dict[str, ChannelAdapter] = {}
        # Per-channel unread counts, incremented only for adapter-dispatched
        # messages (real external channels) — see _on_message. The
        # WebSocket/chat-UI path goes through process_inbound_text() instead,
        # which never touches this, so the user's own dashboard traffic never
        # counts as "unread".
        self._unread_counts: dict[str, int] = {}
        self._gc_interval = gc_interval
        self._gc_task: asyncio.Task | None = None  # type: ignore[type-arg]
        # Direct long-term memory handle — used by the REST API (memory routes)
        # and any caller that needs raw LIKE search/delete without the full
        # 3-tier retrieval pipeline.
        self._long_term = long_term
        # Voice note round-trip: inbound audio attachments are transcribed
        # via stt before the pipeline runs; replies to voice-only messages
        # are synthesized back to audio via tts. Both are best-effort —
        # None disables the corresponding half.
        self._stt = stt
        self._tts = tts
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

        reflection = None
        try:
            from cortexflow_ai.reflection.engine import ReflectionEngine
            reflection = ReflectionEngine(router=router)
        except Exception as exc:
            logger.warning("runtime: reflection engine unavailable (%s)", exc)

        pipeline = CognitivePipeline(
            router=router,
            memory=memory,
            workspace=workspace_files,
            agent_name=cfg.agent.name,
            reflection=reflection,
        )
        session_mgr = SessionManager()
        long_term = LongTermMemory(db_path=os.path.expanduser(cfg.memory.sqlite_path))

        stt = None
        try:
            if getattr(cfg.voice, "stt", "whisper") != "none":
                from cortexflow_ai.voice.stt import WhisperSTT
                stt = WhisperSTT(model_size=getattr(cfg.voice, "stt_model", "base"))
        except Exception as exc:
            logger.warning("runtime: STT unavailable (%s)", exc)

        tts = None
        try:
            if getattr(cfg.voice, "tts_engine", "kokoro") != "none":
                from cortexflow_ai.voice.tts import TTSEngine
                tts = TTSEngine(
                    elevenlabs_api_key=getattr(cfg.voice, "elevenlabs_api_key", None),
                    elevenlabs_voice_id=getattr(cfg.voice, "elevenlabs_voice_id", None) or None,
                )
        except Exception as exc:
            logger.warning("runtime: TTS unavailable (%s)", exc)

        adapters = _build_adapters(cfg)
        return cls(
            pipeline=pipeline,
            session_mgr=session_mgr,
            adapters=adapters,
            long_term=long_term,
            stt=stt,
            tts=tts,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def register_adapter(self, adapter: ChannelAdapter) -> None:
        adapter.on_message(self._on_message)
        self._adapters[adapter.channel_id] = adapter

    async def start(self) -> None:
        """Initialise long-term memory, connect all adapters, start the GC loop."""
        if self._long_term is not None:
            try:
                await self._long_term.init_schema()
            except Exception as exc:
                logger.error("runtime: long-term memory schema init failed: %s", exc)

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
        """Adapter callback: compute a reply and send it back via the adapter."""
        self._unread_counts[msg.channel] = self._unread_counts.get(msg.channel, 0) + 1
        is_voice = await self._maybe_transcribe(msg)
        reply = await self._reply_for(msg)
        await self._send_reply(msg, reply, as_voice=is_voice)

    def get_unread_count(self, channel_id: str) -> int:
        """Unread message count for *channel_id*, 0 if none or unknown."""
        return self._unread_counts.get(channel_id, 0)

    def mark_channel_read(self, channel_id: str) -> None:
        """Reset the unread count for *channel_id* to 0."""
        self._unread_counts[channel_id] = 0

    @property
    def total_unread(self) -> int:
        return sum(self._unread_counts.values())

    async def _maybe_transcribe(self, msg: InboundMessage) -> bool:
        """Transcribe an audio attachment into msg.text when msg has no text.

        Mutates *msg.text* in place so the rest of the pipeline (slash
        commands, CognitivePipeline) sees the transcript like any other
        text message. Returns True if a voice note was transcribed, so the
        caller knows to reply in kind via TTS.
        """
        if (msg.text or "").strip():
            return False

        audio = next((a for a in msg.attachments if a.type == "audio"), None)
        if audio is None or self._stt is None:
            return False

        audio_bytes = audio.data
        if audio_bytes is None and audio.url:
            audio_bytes = await self._fetch_attachment_bytes(audio.url)
        if audio_bytes is None:
            return False

        try:
            transcript = (await self._stt.transcribe(audio_bytes)).strip()
        except Exception as exc:
            logger.warning("runtime: STT transcription failed: %s", exc)
            return False

        if not transcript:
            return False

        msg.text = transcript
        logger.info(
            "runtime: transcribed voice note %s/%s -> %r",
            msg.channel, msg.sender_id[:8], transcript[:60],
        )
        return True

    async def _fetch_attachment_bytes(self, url: str) -> bytes | None:
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=15.0)
                resp.raise_for_status()
                return resp.content
        except Exception as exc:
            logger.warning("runtime: failed to fetch attachment %s: %s", url, exc)
            return None

    async def process_inbound_text(
        self,
        channel: str,
        sender_id: str,
        text: str,
        *,
        sender_name: str = "web",
    ) -> str:
        """Process a message from a non-adapter caller (e.g. the WebSocket UI).

        Runs the same dispatch path as an adapter message but returns the
        reply string directly instead of sending it through a channel adapter.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=None,
            timestamp=time.time(),
            raw={},
        )
        return await self._reply_for(msg)

    async def process_inbound_text_stream(
        self,
        channel: str,
        sender_id: str,
        text: str,
        *,
        sender_name: str = "web",
    ) -> AsyncIterator[PipelineStreamChunk]:
        """Streaming counterpart to process_inbound_text().

        Slash commands are not streamed (they're synchronous/instant by
        nature) — yields the full command reply as a single done=True
        chunk. Normal messages stream incrementally via
        CognitivePipeline.run_stream(), with the same metrics bookkeeping
        _reply_for() does for the non-streaming path.
        """
        msg = InboundMessage(
            channel=channel,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=None,
            timestamp=time.time(),
            raw={},
        )

        self.metrics.messages_received += 1
        REGISTRY.inc("messages_total", labels={"channel": msg.channel})
        REGISTRY.set("active_sessions", float(self._sessions.active_count))

        stripped = (msg.text or "").strip()
        if stripped.startswith("/"):
            cmd = stripped.split()[0].lower()
            if cmd in _SLASH_COMMANDS:
                reply = await self._command_reply(cmd, msg)
                self.metrics.messages_sent += 1
                yield PipelineStreamChunk(
                    done=True,
                    result=PipelineResult(
                        response=reply, model="", provider="", intent="command", task_type="command",
                    ),
                )
                return

        session = self._sessions.get_or_create(msg.channel, msg.sender_id)
        try:
            async for chunk in self._pipeline.run_stream(msg, session):
                if chunk.error:
                    self.metrics.errors += 1
                    REGISTRY.inc("messages_errors_total", labels={"channel": msg.channel})
                    logger.error(
                        "runtime: pipeline stream error for %s/%s: %s",
                        msg.channel, msg.sender_id, chunk.error,
                    )
                    yield PipelineStreamChunk(
                        done=True, error="Sorry, something went wrong. Please try again."
                    )
                    return
                if chunk.done and chunk.result is not None:
                    result = chunk.result
                    self.metrics.pipeline_latency_ms_total += result.latency_ms
                    self.metrics.messages_sent += 1
                    REGISTRY.inc("generation_requests_total", labels={"model": result.model})
                    REGISTRY.observe(
                        "generation_latency_ms", result.latency_ms, labels={"model": result.model}
                    )
                    input_tokens = result.usage.get("input_tokens")
                    if input_tokens:
                        REGISTRY.inc(
                            "tokens_total", input_tokens,
                            labels={"model": result.model, "direction": "input"},
                        )
                    output_tokens = result.usage.get("output_tokens")
                    if output_tokens:
                        REGISTRY.inc(
                            "tokens_total", output_tokens,
                            labels={"model": result.model, "direction": "output"},
                        )
                    logger.info(
                        "runtime: %s/%s → %s (%.0fms) [streamed]",
                        msg.channel, msg.sender_id[:8], result.model, result.latency_ms,
                    )
                    self._store_conversation(msg.channel, stripped, result.response)
                yield chunk
        except Exception as exc:
            self.metrics.errors += 1
            REGISTRY.inc("messages_errors_total", labels={"channel": msg.channel})
            logger.error("runtime: pipeline error for %s/%s: %s", msg.channel, msg.sender_id, exc)
            yield PipelineStreamChunk(done=True, error="Sorry, something went wrong. Please try again.")

    async def _reply_for(self, msg: InboundMessage) -> str:
        """Compute the assistant's reply for an inbound message.

        Shared by adapter dispatch (`_on_message`) and direct callers
        (`process_inbound_text`). Updates both the private RuntimeMetrics and
        the global Prometheus REGISTRY.
        """
        self.metrics.messages_received += 1
        REGISTRY.inc("messages_total", labels={"channel": msg.channel})
        REGISTRY.set("active_sessions", float(self._sessions.active_count))

        text = (msg.text or "").strip()

        # Handle built-in slash commands
        if text.startswith("/"):
            cmd = text.split()[0].lower()
            if cmd in _SLASH_COMMANDS:
                reply = await self._command_reply(cmd, msg)
                self.metrics.messages_sent += 1
                return reply

        # Normal message → cognitive pipeline
        session = self._sessions.get_or_create(msg.channel, msg.sender_id)
        try:
            result: PipelineResult = await self._pipeline.run(msg, session)
            self.metrics.pipeline_latency_ms_total += result.latency_ms
            self.metrics.messages_sent += 1
            REGISTRY.inc("generation_requests_total", labels={"model": result.model})
            REGISTRY.observe(
                "generation_latency_ms", result.latency_ms, labels={"model": result.model}
            )
            input_tokens = result.usage.get("input_tokens")
            if input_tokens:
                REGISTRY.inc(
                    "tokens_total", input_tokens, labels={"model": result.model, "direction": "input"}
                )
            output_tokens = result.usage.get("output_tokens")
            if output_tokens:
                REGISTRY.inc(
                    "tokens_total", output_tokens, labels={"model": result.model, "direction": "output"}
                )
            logger.info(
                "runtime: %s/%s → %s (%.0fms)",
                msg.channel, msg.sender_id[:8], result.model, result.latency_ms,
            )
            self._store_conversation(msg.channel, text, result.response)
            return result.response
        except Exception as exc:
            self.metrics.errors += 1
            REGISTRY.inc("messages_errors_total", labels={"channel": msg.channel})
            logger.error("runtime: pipeline error for %s/%s: %s", msg.channel, msg.sender_id, exc)
            return "Sorry, something went wrong. Please try again."

    def _store_conversation(self, channel: str, user_text: str, response: str) -> None:
        """Fire-and-forget: persist the exchange to long-term SQLite memory."""
        if self._long_term is None:
            return
        content = f"User: {user_text}\nAssistant: {response}"
        asyncio.create_task(
            self._long_term.store(
                session_id=channel,
                content=content,
                importance=0.5,
                memory_type="conversation",
            )
        )

    async def _send_reply(
        self, original: InboundMessage, text: str, *, as_voice: bool = False
    ) -> None:
        adapter = self._adapters.get(original.channel)
        if not adapter:
            logger.warning("runtime: no adapter for channel %s", original.channel)
            return

        attachments: list[Attachment] | None = None
        if as_voice and self._tts is not None:
            audio = await self._synthesize_reply(text)
            if audio:
                attachments = [Attachment(type="audio", data=audio, mime_type="audio/mpeg")]

        await adapter.send(
            original.sender_id, text, reply_to=original.reply_to_id, attachments=attachments
        )

    async def _synthesize_reply(self, text: str) -> bytes | None:
        try:
            return await self._tts.synthesize(text)
        except Exception as exc:
            logger.warning("runtime: TTS synthesis failed: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Built-in commands
    # ------------------------------------------------------------------

    async def _command_reply(self, cmd: str, msg: InboundMessage) -> str:
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

        return reply

    # ------------------------------------------------------------------
    # GC loop
    # ------------------------------------------------------------------

    async def _gc_loop(self) -> None:
        while True:
            await asyncio.sleep(self._gc_interval)
            removed = self._sessions.gc()
            REGISTRY.set("active_sessions", float(self._sessions.active_count))
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
            from cortexflow_ai.channels.telegram import TelegramAdapter
            return TelegramAdapter(config)
        if name == "discord":
            from cortexflow_ai.channels.discord_ import DiscordAdapter
            return DiscordAdapter(config)
        if name == "slack":
            from cortexflow_ai.channels.slack import SlackAdapter
            return SlackAdapter(config)
        if name == "whatsapp":
            from cortexflow_ai.channels.whatsapp import WhatsAppAdapter
            return WhatsAppAdapter(config)
        if name == "email":
            from cortexflow_ai.channels.email_ import EmailAdapter
            return EmailAdapter(config)
    except Exception as exc:
        logger.warning("runtime: could not load adapter %s: %s", name, exc)
    logger.debug("runtime: unknown channel %s — skipping", name)
    return None
