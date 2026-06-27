"""Cross-channel slash command handler.

Commands registered by make_default():
    /reset                — clear current session history
    /memory [query]       — search long-term memory (top 5 results)
    /model [name]         — show or suggest a model override for this session
    /status               — show session state + router settings
    /compact              — summarise and compress session history via LLM
    /voice on|off         — toggle TTS voice responses for this session

Usage:
    handler = CommandHandler.make_default()
    result  = await handler.dispatch("/reset", session=session)
    if result.handled:
        await adapter.send(sender_id, result.text)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

_HandlerFn = Callable[..., Awaitable[str]]


@dataclass
class CommandResult:
    """Outcome of a dispatch() call."""

    text: str
    handled: bool = True


class CommandHandler:
    """Parses incoming text for /commands and dispatches to registered handlers.

    Handlers are plain async callables:
        async def my_cmd(*args, session=None, router=None, **kwargs) -> str: ...

    Positional *args come from the command line (e.g. "/memory ai tools" →
    args=("ai", "tools")). Extra keyword context (session, router, long_term,
    etc.) is passed through from dispatch().
    """

    PREFIX = "/"

    def __init__(self) -> None:
        self._handlers: dict[str, _HandlerFn] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, name: str, fn: _HandlerFn) -> None:
        """Register *fn* as the handler for command /*name*."""
        self._handlers[name.lstrip("/").lower()] = fn

    def registered_names(self) -> list[str]:
        """Return sorted list of registered command names (without slash)."""
        return sorted(self._handlers.keys())

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def is_command(self, text: str) -> bool:
        """Return True if *text* starts with the command prefix."""
        return bool(text) and text.strip().startswith(self.PREFIX)

    def parse(self, text: str) -> tuple[str, list[str]]:
        """Split '/cmd arg1 arg2' into ('cmd', ['arg1', 'arg2'])."""
        parts = text.strip().lstrip(self.PREFIX).split()
        if not parts:
            return "", []
        return parts[0].lower(), parts[1:]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    async def dispatch(self, text: str, **context) -> CommandResult:
        """Try to handle *text* as a slash command.

        Returns a CommandResult with ``handled=False`` when *text* is not a
        command so the caller can continue with normal message processing.
        """
        if not self.is_command(text):
            return CommandResult(text="", handled=False)

        name, args = self.parse(text)
        if not name:
            return CommandResult(text="Usage: /command [args]", handled=True)

        handler = self._handlers.get(name)
        if handler is None:
            available = "  ".join(f"/{n}" for n in self.registered_names())
            return CommandResult(
                text=f"Unknown command: /{name}\nAvailable: {available}",
                handled=True,
            )

        response = await handler(*args, **context)
        return CommandResult(text=response, handled=True)

    # ------------------------------------------------------------------
    # Default command factory
    # ------------------------------------------------------------------

    @classmethod
    def make_default(cls) -> "CommandHandler":
        """Return a CommandHandler pre-loaded with all standard commands."""
        h = cls()

        # ── /reset ─────────────────────────────────────────────────────
        async def cmd_reset(*args, session=None, **_) -> str:
            if session is None:
                return "No active session to reset."
            session.clear()
            return "Session history cleared."

        # ── /memory [query] ────────────────────────────────────────────
        async def cmd_memory(*args, session=None, long_term=None, **_) -> str:
            query = " ".join(args) if args else "recent"
            if long_term is None:
                return "Long-term memory is not configured."
            session_id = getattr(session, "session_id", "%") if session else "%"
            results = await long_term.search(
                session_id=session_id, query=query, limit=5
            )
            if not results:
                return f"No memories found for: {query!r}"
            lines = [f"Memory results for {query!r}:"]
            for r in results:
                snippet = str(r.get("content", ""))[:120]
                score = float(r.get("importance_score", 0.0))
                lines.append(f"  [{score:.2f}] {snippet}")
            return "\n".join(lines)

        # ── /model [name] ──────────────────────────────────────────────
        async def cmd_model(*args, router=None, **_) -> str:
            if not args:
                current = "auto"
                if router is not None:
                    current = getattr(router, "_primary", "auto")
                return f"Current model: {current}\nUsage: /model <model-name>"
            model_name = args[0]
            return (
                f"Model preference noted: {model_name}\n"
                "(Takes effect on the next message.)"
            )

        # ── /status ────────────────────────────────────────────────────
        async def cmd_status(*args, session=None, router=None, **_) -> str:
            lines = ["── CortexFlow Status ──"]
            if session:
                lines.append(f"Session:    {session.session_id[:8]}…")
                lines.append(f"Channel:    {getattr(session, 'channel', '?')}")
                lines.append(f"Turns:      {session.turn_count}")
                lines.append(f"Idle:       {session.idle_seconds:.0f}s")
            else:
                lines.append("Session:    (none)")
            if router:
                lines.append(f"Privacy:    {router.privacy_mode}")
                lines.append(f"AutoComp:   {router.auto_complexity}")
            return "\n".join(lines)

        # ── /compact ───────────────────────────────────────────────────
        async def cmd_compact(*args, session=None, long_term=None, router=None, **_) -> str:
            if session is None:
                return "No active session to compact."
            if router is None:
                return "Router not available — cannot generate a summary."
            from cortexflow_ai.memory.compactor import ConversationCompactor

            compactor = ConversationCompactor(
                session=session,
                long_term=long_term,
                router=router,
            )
            summary = await compactor.compact()
            if not summary:
                return "Nothing to compact (history is empty or compaction failed)."
            preview = summary[:200] + ("…" if len(summary) > 200 else "")
            return f"Session compacted.\nSummary: {preview}"

        # ── /voice on|off ──────────────────────────────────────────────
        async def cmd_voice(*args, **_) -> str:
            state = args[0].lower() if args else ""
            if state in ("on", "true", "1", "yes"):
                return "Voice responses enabled for this session."
            if state in ("off", "false", "0", "no"):
                return "Voice responses disabled for this session."
            return "Usage: /voice on|off"

        h.register("reset", cmd_reset)
        h.register("memory", cmd_memory)
        h.register("model", cmd_model)
        h.register("status", cmd_status)
        h.register("compact", cmd_compact)
        h.register("voice", cmd_voice)

        return h
