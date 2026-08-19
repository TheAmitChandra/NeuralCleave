"""Persistent exec-approval allowlist — glob command patterns + optional
regex argument patterns, with configurable security/ask modes.

P5 of the 2026-08-17 gap analysis: before this, ApprovalQueue (see
``neuralcleave/tools/approvals.py``) had no persistent allowlist and no
security/ask modes — every gated command always prompted, every time,
forever, with no way to durably trust a known-safe command.

Mirrors the SQLite persistence pattern in ``neuralcleave/privacy/audit.py``.
Default db_path: ``~/.neuralcleave/approval_policy.db`` (override via
``NEURALCLEAVE_APPROVAL_DB_PATH``).

security modes:
    "deny"       - nothing is auto-approved and nothing is prompted either;
                   every gated command is denied outright.
    "allowlist"  - commands matching a stored entry are auto-approved;
                   others fall through to the ``ask`` mode.
    "full"       - every gated command is auto-approved (gate disabled).

ask modes (only consulted when security == "allowlist"):
    "off"        - never prompt; an unmatched command is denied silently.
    "on-miss"    - prompt only when no allowlist entry matches (default).
    "always"     - always prompt, even when an allowlist entry matches.

Usage::

    from neuralcleave.tools.approval_policy import POLICY

    if POLICY.should_auto_approve("git", "git log --oneline"):
        ...  # run without prompting
    elif POLICY.should_prompt("git", "git log --oneline"):
        ...  # queue an ApprovalRequest
    else:
        ...  # denied outright, no prompt
"""

from __future__ import annotations

import fnmatch
import os
import re
import sqlite3
import time
from dataclasses import dataclass

DEFAULT_DB_PATH = os.getenv("NEURALCLEAVE_APPROVAL_DB_PATH") or "~/.neuralcleave/approval_policy.db"

VALID_SECURITY_MODES = ("deny", "allowlist", "full")
VALID_ASK_MODES = ("off", "on-miss", "always")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS allowlist_entries (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    pattern     TEXT    NOT NULL,
    arg_pattern TEXT,
    created_at  REAL    NOT NULL
);
"""


@dataclass
class AllowlistEntry:
    """One persisted allowlist entry."""

    id: int
    pattern: str
    arg_pattern: str | None
    created_at: float

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern": self.pattern,
            "arg_pattern": self.arg_pattern,
            "created_at": self.created_at,
        }

    def matches(self, command: str, args: str) -> bool:
        """Whether *command* (a program name) and *args* (the full command
        line, for regex matching) satisfy this entry."""
        if not fnmatch.fnmatch(command, self.pattern):
            return False
        if self.arg_pattern:
            return re.search(self.arg_pattern, args) is not None
        return True


class ApprovalPolicy:
    """Persistent allowlist + security/ask mode decision engine.

    Args:
        db_path: SQLite database path (``~`` expanded), or ``None`` for
            in-memory-only behaviour (what tests get by default).
        security: One of ``VALID_SECURITY_MODES``.
        ask: One of ``VALID_ASK_MODES``.
    """

    def __init__(
        self,
        db_path: str | None = DEFAULT_DB_PATH,
        security: str = "allowlist",
        ask: str = "on-miss",
    ) -> None:
        if security not in VALID_SECURITY_MODES:
            raise ValueError(f"Invalid security mode: {security!r} (must be one of {VALID_SECURITY_MODES})")
        if ask not in VALID_ASK_MODES:
            raise ValueError(f"Invalid ask mode: {ask!r} (must be one of {VALID_ASK_MODES})")
        self.security = security
        self.ask = ask
        self._entries: list[AllowlistEntry] = []
        self._next_id = 1
        self._db: sqlite3.Connection | None = None
        if db_path:
            expanded = os.path.expanduser(db_path)
            parent = os.path.dirname(expanded)
            if parent:
                os.makedirs(parent, exist_ok=True)
            self._db = sqlite3.connect(expanded, check_same_thread=False)
            self._db.execute(_CREATE_TABLE)
            self._db.commit()
            self._load_from_db()

    def _load_from_db(self) -> None:
        if self._db is None:
            return
        cursor = self._db.execute(
            "SELECT id, pattern, arg_pattern, created_at FROM allowlist_entries ORDER BY id"
        )
        self._entries = [
            AllowlistEntry(id=row[0], pattern=row[1], arg_pattern=row[2], created_at=row[3])
            for row in cursor.fetchall()
        ]
        if self._entries:
            self._next_id = max(e.id for e in self._entries) + 1

    # ------------------------------------------------------------------
    # Allowlist CRUD
    # ------------------------------------------------------------------

    def add_entry(self, pattern: str, arg_pattern: str | None = None) -> AllowlistEntry:
        """Add a new allowlist entry, kept in memory and mirrored to SQLite
        when persistence is enabled (``db_path`` was given)."""
        now = time.time()
        if self._db is not None:
            cursor = self._db.execute(
                "INSERT INTO allowlist_entries (pattern, arg_pattern, created_at) VALUES (?, ?, ?)",
                (pattern, arg_pattern, now),
            )
            self._db.commit()
            entry_id = cursor.lastrowid
        else:
            entry_id = self._next_id
            self._next_id += 1
        entry = AllowlistEntry(id=entry_id, pattern=pattern, arg_pattern=arg_pattern, created_at=now)
        self._entries.append(entry)
        return entry

    def list_entries(self) -> list[AllowlistEntry]:
        return list(self._entries)

    def remove_entry(self, entry_id: int) -> bool:
        before = len(self._entries)
        self._entries = [e for e in self._entries if e.id != entry_id]
        removed = len(self._entries) != before
        if removed and self._db is not None:
            self._db.execute("DELETE FROM allowlist_entries WHERE id = ?", (entry_id,))
            self._db.commit()
        return removed

    def matches(self, command: str, args: str = "") -> bool:
        """Whether any stored entry matches *command*/*args*."""
        return any(e.matches(command, args) for e in self._entries)

    # ------------------------------------------------------------------
    # Decisions
    # ------------------------------------------------------------------

    def should_auto_approve(self, command: str, args: str = "") -> bool:
        """Whether *command* should run without prompting at all."""
        if self.security == "full":
            return True
        if self.security == "deny":
            return False
        # security == "allowlist"
        if self.ask == "always":
            return False  # always prompt, even on a match
        return self.matches(command, args)

    def should_prompt(self, command: str, args: str = "") -> bool:
        """Whether the user should be asked (as opposed to a silent deny)."""
        if self.security in ("full", "deny"):
            return False
        if self.ask == "off":
            return False
        if self.ask == "always":
            return True
        # ask == "on-miss"
        return not self.matches(command, args)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


POLICY: ApprovalPolicy = ApprovalPolicy()
