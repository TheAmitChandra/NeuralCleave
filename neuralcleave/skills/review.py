"""Skill review queue — agent-authored skills go through a
propose -> apply/reject/quarantine lifecycle instead of loading immediately.

P8 of the 2026-08-17 gap analysis: ``SkillWriter.write_skill()`` previously
wrote AND loaded agent-authored code in one step, with no review at all.
``WriteSkillTool`` (the agent-facing tool) now calls
``SkillWriter.propose_skill()`` instead, which validates and persists a
pending :class:`SkillProposal` but does **not** write to the skills
directory or load it — a human decides via ``neuralcleave skills review
approve|reject <id>`` (or the matching REST routes), matching OpenClaw's
Skill Workshop propose/apply/reject/quarantine model, scoped to that core
lifecycle (no background self-learning history scanner in this round).

``SkillWriter.write_skill()`` itself is unchanged and still writes+loads
immediately — that remains the trusted path for e.g. the skills gallery
installer, which is not agent-authored code needing review.

Mirrors the SQLite persistence pattern in ``neuralcleave/tools/approval_policy.py``.
Default db_path: ``~/.neuralcleave/skill_review.db`` (override via
``NEURALCLEAVE_SKILL_REVIEW_DB_PATH``).
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass

DEFAULT_DB_PATH = os.getenv("NEURALCLEAVE_SKILL_REVIEW_DB_PATH") or "~/.neuralcleave/skill_review.db"

VALID_STATUSES: tuple[str, ...] = ("pending", "applied", "rejected")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS skill_proposals (
    id          TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    code        TEXT    NOT NULL,
    description TEXT    NOT NULL DEFAULT '',
    status      TEXT    NOT NULL DEFAULT 'pending',
    created_at  REAL    NOT NULL,
    decided_at  REAL
);
"""


@dataclass
class SkillProposal:
    """One agent-authored skill awaiting (or past) human review."""

    id: str
    name: str
    code: str
    description: str
    status: str
    created_at: float
    decided_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": self.decided_at,
        }


class SkillReviewQueue:
    """Persistent queue of skill proposals awaiting human review.

    Args:
        db_path: SQLite database path (``~`` expanded), or ``None`` for
            in-memory-only behaviour (what tests get by default).
    """

    def __init__(self, db_path: str | None = DEFAULT_DB_PATH) -> None:
        self._entries: dict[str, SkillProposal] = {}
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
            "SELECT id, name, code, description, status, created_at, decided_at "
            "FROM skill_proposals ORDER BY created_at"
        )
        for row in cursor.fetchall():
            self._entries[row[0]] = SkillProposal(
                id=row[0], name=row[1], code=row[2], description=row[3],
                status=row[4], created_at=row[5], decided_at=row[6],
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def propose(self, name: str, code: str, description: str = "") -> SkillProposal:
        """Create a new pending proposal. Never touches disk or loads code."""
        proposal = SkillProposal(
            id=str(uuid.uuid4()), name=name, code=code, description=description,
            status="pending", created_at=time.time(),
        )
        self._entries[proposal.id] = proposal
        if self._db is not None:
            self._db.execute(
                "INSERT INTO skill_proposals "
                "(id, name, code, description, status, created_at, decided_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.id, proposal.name, proposal.code, proposal.description,
                    proposal.status, proposal.created_at, proposal.decided_at,
                ),
            )
            self._db.commit()
        return proposal

    def get(self, proposal_id: str) -> SkillProposal | None:
        return self._entries.get(proposal_id)

    def list_pending(self) -> list[SkillProposal]:
        return [p for p in self._entries.values() if p.status == "pending"]

    def list_all(self) -> list[SkillProposal]:
        return list(self._entries.values())

    def _set_status(self, proposal_id: str, status: str) -> SkillProposal | None:
        """Transition a pending proposal. Returns None if not found or not pending."""
        proposal = self._entries.get(proposal_id)
        if proposal is None or proposal.status != "pending":
            return None
        proposal.status = status
        proposal.decided_at = time.time()
        if self._db is not None:
            self._db.execute(
                "UPDATE skill_proposals SET status = ?, decided_at = ? WHERE id = ?",
                (status, proposal.decided_at, proposal_id),
            )
            self._db.commit()
        return proposal

    def mark_applied(self, proposal_id: str) -> SkillProposal | None:
        return self._set_status(proposal_id, "applied")

    def mark_rejected(self, proposal_id: str) -> SkillProposal | None:
        return self._set_status(proposal_id, "rejected")

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


REVIEW_QUEUE: SkillReviewQueue = SkillReviewQueue()
