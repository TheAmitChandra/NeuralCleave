"""Voice session lifecycle tracker.

Tracks the boundary between consecutive voice conversations, allowing the
runtime to distinguish between utterances that belong to the same voice session
and those that start a new one after an extended silence.

A *voice session* begins with the first utterance after a period of inactivity
and ends when either:
- The caller invokes :meth:`VoiceSessionTracker.reset` explicitly (e.g. the
  user says "start over" or presses a UI reset button).
- A new utterance arrives after the session has been idle for longer than
  ``idle_timeout_s`` seconds, causing the tracker to auto-rotate.

Usage::

    tracker = VoiceSessionTracker(idle_timeout_s=300.0)

    # On each voice utterance:
    new_session = tracker.on_utterance()
    if new_session:
        print("New voice session started:", tracker.session_id)
"""

from __future__ import annotations

import time
import uuid


class VoiceSessionTracker:
    """Tracks voice session boundaries based on utterance timing.

    Args:
        idle_timeout_s: Seconds of silence after which the next utterance
                        is treated as a new voice session.  Default 300 (5 min).
    """

    def __init__(self, *, idle_timeout_s: float = 300.0) -> None:
        self._idle_timeout_s = float(idle_timeout_s)
        self._session_id: str = str(uuid.uuid4())
        self._started_at: float = time.time()
        self._last_utterance_at: float = 0.0
        self._turn_count: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """UUID of the current voice session."""
        return self._session_id

    @property
    def turn_count(self) -> int:
        """Number of utterances processed in the current session."""
        return self._turn_count

    @property
    def idle_timeout_s(self) -> float:
        """Seconds of silence that trigger a new session on the next utterance."""
        return self._idle_timeout_s

    @property
    def is_active(self) -> bool:
        """``True`` if at least one utterance has been processed and the session
        has not yet timed out."""
        if self._turn_count == 0 or self._last_utterance_at == 0.0:
            return False
        return (time.time() - self._last_utterance_at) < self._idle_timeout_s

    @property
    def idle_seconds(self) -> float:
        """Seconds since the last utterance, or 0.0 if none yet."""
        if self._last_utterance_at == 0.0:
            return 0.0
        return time.time() - self._last_utterance_at

    @property
    def started_at(self) -> float:
        """Unix timestamp when the current session started."""
        return self._started_at

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_utterance(self) -> bool:
        """Record an incoming utterance and return whether a new session started.

        If the gap since the last utterance exceeds ``idle_timeout_s``, the
        current session is rotated (new ``session_id``, ``turn_count`` reset to
        1).  Returns ``True`` when a new session was started.
        """
        now = time.time()
        new_session = False
        if (
            self._turn_count > 0
            and self._last_utterance_at > 0.0
            and (now - self._last_utterance_at) >= self._idle_timeout_s
        ):
            self._rotate(now)
            new_session = True
        self._last_utterance_at = now
        self._turn_count += 1
        return new_session

    def reset(self) -> str:
        """Explicitly start a new voice session and return the new session ID."""
        self._rotate(time.time())
        return self._session_id

    def info(self) -> dict[str, object]:
        """Return a snapshot dict suitable for JSON serialisation."""
        return {
            "session_id": self._session_id,
            "turn_count": self._turn_count,
            "is_active": self.is_active,
            "idle_seconds": round(self.idle_seconds, 1),
            "idle_timeout_s": self._idle_timeout_s,
            "started_at": self._started_at,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _rotate(self, now: float) -> None:
        self._session_id = str(uuid.uuid4())
        self._started_at = now
        self._last_utterance_at = 0.0
        self._turn_count = 0
