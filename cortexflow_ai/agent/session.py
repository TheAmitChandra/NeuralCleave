"""Per-channel session state management.

Each active channel connection gets one Session. Sessions hold:
- Short conversation history (last N turns, kept in memory)
- The channel ID and sender ID that owns the session
- Metadata: created_at, last_active, turn count

Sessions are intentionally lightweight — heavy memory is offloaded to the
3-tier MemoryRetrievalPipeline. The in-process history is only the rolling
window of the current conversation needed for immediate context continuity.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Literal

Role = Literal["user", "assistant", "system"]


@dataclass
class Turn:
    """One exchange in a conversation."""

    role: Role
    content: str
    timestamp: float = field(default_factory=time.time)
    model: str | None = None  # model that generated this turn (assistant only)

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp,
            "model": self.model,
        }


class Session:
    """Conversation state for one user on one channel.

    Args:
        channel:    Channel ID ("telegram", "discord", etc.)
        sender_id:  Platform-specific user identifier.
        max_turns:  Rolling window size — older turns are dropped.
                    Default 20 keeps ~10 back-and-forth exchanges in memory.
    """

    def __init__(
        self,
        channel: str,
        sender_id: str,
        *,
        max_turns: int = 20,
    ) -> None:
        self.session_id: str = str(uuid.uuid4())
        self.channel = channel
        self.sender_id = sender_id
        self.max_turns = max_turns
        self.created_at: float = time.time()
        self.last_active: float = self.created_at
        self.turn_count: int = 0
        self._history: list[Turn] = []

    # ------------------------------------------------------------------
    # History management
    # ------------------------------------------------------------------

    def add_turn(self, role: Role, content: str, *, model: str | None = None) -> Turn:
        """Append a turn and enforce the rolling window."""
        turn = Turn(role=role, content=content, model=model)
        self._history.append(turn)
        if len(self._history) > self.max_turns:
            self._history = self._history[-self.max_turns:]
        self.last_active = time.time()
        self.turn_count += 1
        return turn

    def history(self) -> list[Turn]:
        """Return a copy of the current history window."""
        return list(self._history)

    def history_as_dicts(self) -> list[dict]:
        """Return history as a list of dicts, compatible with LLM message arrays."""
        return [t.to_dict() for t in self._history]

    def clear(self) -> None:
        """Reset conversation history (e.g., on /reset command)."""
        self._history.clear()
        self.turn_count = 0

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def build_prompt(self, *, include_turns: int | None = None) -> str:
        """Build a plain-text conversation transcript for LLM prompt injection.

        Args:
            include_turns: Limit to the last N turns. None = all in window.
        """
        turns = self._history[-include_turns:] if include_turns else self._history
        lines: list[str] = []
        for t in turns:
            prefix = "User" if t.role == "user" else "Assistant"
            lines.append(f"{prefix}: {t.content}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_fresh(self) -> bool:
        """True if no user turns have been recorded yet."""
        return not any(t.role == "user" for t in self._history)

    @property
    def idle_seconds(self) -> float:
        return time.time() - self.last_active

    def __repr__(self) -> str:
        return (
            f"Session(id={self.session_id[:8]}, channel={self.channel!r}, "
            f"sender={self.sender_id!r}, turns={self.turn_count})"
        )


class SessionManager:
    """Registry of active sessions, keyed by (channel, sender_id).

    Sessions expire after ``idle_timeout`` seconds to free memory.
    Call ``gc()`` periodically or rely on the runtime to do so.
    """

    def __init__(self, idle_timeout: float = 1800.0, max_turns: int = 20) -> None:
        self._idle_timeout = idle_timeout
        self._max_turns = max_turns
        self._sessions: dict[tuple[str, str], Session] = {}

    def get_or_create(self, channel: str, sender_id: str) -> Session:
        """Return existing session or create a new one."""
        key = (channel, sender_id)
        if key not in self._sessions:
            self._sessions[key] = Session(channel, sender_id, max_turns=self._max_turns)
        return self._sessions[key]

    def get(self, channel: str, sender_id: str) -> Session | None:
        return self._sessions.get((channel, sender_id))

    def remove(self, channel: str, sender_id: str) -> None:
        self._sessions.pop((channel, sender_id), None)

    def gc(self) -> int:
        """Remove sessions idle longer than ``idle_timeout``. Returns count removed."""
        expired = [
            key for key, s in self._sessions.items()
            if s.idle_seconds > self._idle_timeout
        ]
        for key in expired:
            del self._sessions[key]
        return len(expired)

    @property
    def active_count(self) -> int:
        return len(self._sessions)
