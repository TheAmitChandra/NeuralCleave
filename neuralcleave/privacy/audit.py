"""Session-scoped outbound HTTP call log.

Provides a module-level ``AUDIT_LOG`` singleton that any component can write to
when it makes an outbound HTTP request.  The gateway exposes this log via
``GET /api/v1/privacy/report`` so users can inspect exactly which external
services NeuralCleave contacted during a session.

Usage::

    from neuralcleave.privacy.audit import AUDIT_LOG

    AUDIT_LOG.record(
        session_id="abc",
        method="POST",
        url="https://api.openai.com/v1/chat/completions",
    )
    entries = AUDIT_LOG.entries_for_session("abc")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import urlparse


@dataclass
class AuditEntry:
    """One recorded outbound HTTP call."""

    session_id: str
    method: str
    url: str
    destination: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "method": self.method,
            "url": self.url,
            "destination": self.destination,
            "timestamp": self.timestamp,
        }


class PrivacyAuditLog:
    """In-memory store for outbound HTTP call records.

    Thread-safe.  Records are kept per session and can be queried or cleared
    independently.  There is no persistence — the log resets on restart, which
    is intentional: audit is a transparency feature, not a retention feature.
    """

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = Lock()

    def record(
        self,
        *,
        session_id: str,
        method: str,
        url: str,
    ) -> AuditEntry:
        """Record one outbound HTTP call."""
        parsed = urlparse(url)
        destination = parsed.netloc or parsed.path
        entry = AuditEntry(
            session_id=session_id,
            method=method.upper(),
            url=url,
            destination=destination,
        )
        with self._lock:
            self._entries.append(entry)
        return entry

    def entries_for_session(self, session_id: str) -> list[AuditEntry]:
        """Return all entries for one session, in chronological order."""
        with self._lock:
            return [e for e in self._entries if e.session_id == session_id]

    def all_entries(self) -> list[AuditEntry]:
        """Return all entries across all sessions."""
        with self._lock:
            return list(self._entries)

    def unique_destinations(self, session_id: str | None = None) -> list[str]:
        """Return the set of distinct host:port destinations contacted."""
        entries = self.entries_for_session(session_id) if session_id else self.all_entries()
        seen: dict[str, None] = {}
        for e in entries:
            seen[e.destination] = None
        return list(seen)

    def clear_session(self, session_id: str) -> int:
        """Remove all entries for *session_id*.  Returns the number of entries removed."""
        with self._lock:
            before = len(self._entries)
            self._entries = [e for e in self._entries if e.session_id != session_id]
            return before - len(self._entries)

    def clear_all(self) -> int:
        """Remove all entries.  Returns the number of entries removed."""
        with self._lock:
            count = len(self._entries)
            self._entries = []
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


AUDIT_LOG: PrivacyAuditLog = PrivacyAuditLog()
