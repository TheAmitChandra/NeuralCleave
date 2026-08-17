"""Session-scoped outbound HTTP call log.

Provides a module-level ``AUDIT_LOG`` singleton that any component can write to
when it makes an outbound HTTP request.  The gateway exposes this log via
``GET /api/v1/privacy/report`` so users can inspect exactly which external
services NeuralCleave contacted during a session.

The ``AUDIT_LOG`` singleton persists entries to a SQLite database at
``~/.neuralcleave/privacy_audit.db`` (override with the
``NEURALCLEAVE_AUDIT_DB_PATH`` env var) so the audit trail survives a gateway
restart, with entries older than ``DEFAULT_RETENTION_DAYS`` pruned
automatically — durable enough for compliance review, bounded so it isn't an
indefinite log. A bare ``PrivacyAuditLog()`` (no ``db_path``) stays in-memory
only, which is what tests and other short-lived instances get by default.

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

import os
import sqlite3
import time
from dataclasses import dataclass, field
from threading import Lock
from urllib.parse import urlparse

DEFAULT_DB_PATH = os.getenv("NEURALCLEAVE_AUDIT_DB_PATH") or "~/.neuralcleave/privacy_audit.db"
DEFAULT_RETENTION_DAYS = 90

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    method      TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    destination TEXT    NOT NULL,
    timestamp   REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_entries (session_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_entries (timestamp);
"""


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
    """Store for outbound HTTP call records, in-memory or SQLite-backed.

    Thread-safe.  Records are kept per session and can be queried or cleared
    independently.  Pass ``db_path`` to persist entries to SQLite across
    restarts (the module singleton ``AUDIT_LOG`` does this); the default
    ``db_path=None`` keeps the log in-memory only, resetting on restart.

    When persistence is enabled, entries older than ``retention_days`` are
    pruned automatically on load and on every ``record()`` call, keeping the
    durable log bounded rather than growing forever.

    Args:
        db_path: Path to a SQLite database file (``~`` is expanded), or
            ``None`` for in-memory-only behaviour.
        retention_days: How long persisted entries are kept before automatic
            pruning. Ignored when ``db_path`` is ``None``.
    """

    def __init__(
        self,
        db_path: str | None = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
    ) -> None:
        self._entries: list[AuditEntry] = []
        self._lock = Lock()
        self._retention_days = retention_days
        self._db: sqlite3.Connection | None = None
        if db_path:
            expanded = os.path.expanduser(db_path)
            parent = os.path.dirname(expanded)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._db = sqlite3.connect(expanded, check_same_thread=False)
            self._db.executescript(_CREATE_TABLE)
            self._db.commit()
            self._prune_expired_locked()
            self._load_from_db_locked()

    def _cutoff(self) -> float:
        return time.time() - self._retention_days * 86400

    def _prune_expired_locked(self) -> None:
        """Remove entries older than the retention window. Caller must hold ``_lock`` (or be in ``__init__``)."""
        if self._db is None:
            return
        cutoff = self._cutoff()
        self._db.execute("DELETE FROM audit_entries WHERE timestamp < ?", (cutoff,))
        self._db.commit()
        self._entries = [e for e in self._entries if e.timestamp >= cutoff]

    def _load_from_db_locked(self) -> None:
        if self._db is None:
            return
        cursor = self._db.execute(
            "SELECT session_id, method, url, destination, timestamp "
            "FROM audit_entries ORDER BY id"
        )
        self._entries = [
            AuditEntry(
                session_id=row[0],
                method=row[1],
                url=row[2],
                destination=row[3],
                timestamp=row[4],
            )
            for row in cursor.fetchall()
        ]

    def prune_expired(self) -> int:
        """Manually prune entries older than the retention window.

        Returns the number of entries removed. No-op (returns 0) when
        persistence is disabled.
        """
        with self._lock:
            before = len(self._entries)
            self._prune_expired_locked()
            return before - len(self._entries)

    def close(self) -> None:
        """Close the underlying SQLite connection, if persistence is enabled."""
        if self._db is not None:
            self._db.close()
            self._db = None

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
            if self._db is not None:
                self._db.execute(
                    "INSERT INTO audit_entries "
                    "(session_id, method, url, destination, timestamp) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (entry.session_id, entry.method, entry.url, entry.destination, entry.timestamp),
                )
                self._db.commit()
                self._prune_expired_locked()
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
            if self._db is not None:
                self._db.execute("DELETE FROM audit_entries WHERE session_id = ?", (session_id,))
                self._db.commit()
            return before - len(self._entries)

    def clear_all(self) -> int:
        """Remove all entries.  Returns the number of entries removed."""
        with self._lock:
            count = len(self._entries)
            self._entries = []
            if self._db is not None:
                self._db.execute("DELETE FROM audit_entries")
                self._db.commit()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)


AUDIT_LOG: PrivacyAuditLog = PrivacyAuditLog(db_path=DEFAULT_DB_PATH)
