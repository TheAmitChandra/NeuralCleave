"""
FailurePatternDetector — identifies recurring failure modes across agent executions.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FailureRecord:
    """A single recorded failure event."""

    record_id: str
    agent_id: str
    task_id: str
    error: str
    context: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_id": self.record_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "error": self.error,
            "context": self.context,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class FailurePattern:
    """An aggregated recurring failure pattern."""

    pattern_id: str
    description: str   # normalised error string used as pattern key
    occurrences: int
    agent_ids: list[str]  # agents that triggered this pattern
    last_seen: datetime

    def to_dict(self) -> dict[str, Any]:
        return {
            "pattern_id": self.pattern_id,
            "description": self.description,
            "occurrences": self.occurrences,
            "agent_ids": self.agent_ids,
            "last_seen": self.last_seen.isoformat(),
        }


# ---------------------------------------------------------------------------
# Detector
# ---------------------------------------------------------------------------

class FailurePatternDetector:
    """
    Records individual failures and detects patterns that repeat above a threshold.

    Pattern key = normalised error string (lower-cased, stripped).
    """

    def __init__(self, default_threshold: int = 2) -> None:
        if default_threshold < 1:
            raise ValueError("default_threshold must be >= 1")
        self.default_threshold = default_threshold
        self._records: list[FailureRecord] = []
        # pattern_key -> list of FailureRecord
        self._by_pattern: dict[str, list[FailureRecord]] = defaultdict(list)
        # Stable pattern IDs so same key always maps to same pattern_id
        self._pattern_ids: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_failure(
        self,
        agent_id: str,
        task_id: str,
        error: str,
        context: dict[str, Any] | None = None,
    ) -> FailureRecord:
        """Record a single failure event."""
        record = FailureRecord(
            record_id=uuid.uuid4().hex,
            agent_id=agent_id,
            task_id=task_id,
            error=error,
            context=context or {},
        )
        self._records.append(record)
        key = self._normalise(error)
        self._by_pattern[key].append(record)
        if key not in self._pattern_ids:
            self._pattern_ids[key] = uuid.uuid4().hex
        return record

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect_patterns(self, threshold: int | None = None) -> list[FailurePattern]:
        """
        Return all patterns whose occurrence count >= threshold.
        Patterns are sorted descending by occurrence count.
        """
        min_count = threshold if threshold is not None else self.default_threshold
        patterns: list[FailurePattern] = []
        for key, records in self._by_pattern.items():
            if len(records) >= min_count:
                agent_ids = list({r.agent_id for r in records})
                last_seen = max(r.timestamp for r in records)
                patterns.append(
                    FailurePattern(
                        pattern_id=self._pattern_ids[key],
                        description=key,
                        occurrences=len(records),
                        agent_ids=agent_ids,
                        last_seen=last_seen,
                    )
                )
        patterns.sort(key=lambda p: p.occurrences, reverse=True)
        return patterns

    # ------------------------------------------------------------------
    # Querying raw records
    # ------------------------------------------------------------------

    def get_records(self, agent_id: str | None = None) -> list[FailureRecord]:
        """Return all failure records, optionally filtered by agent."""
        if agent_id is None:
            return list(self._records)
        return [r for r in self._records if r.agent_id == agent_id]

    @property
    def record_count(self) -> int:
        return len(self._records)

    @property
    def pattern_count(self) -> int:
        """Return how many distinct error patterns have been seen."""
        return len(self._by_pattern)

    def clear(self) -> None:
        self._records.clear()
        self._by_pattern.clear()
        self._pattern_ids.clear()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise(error: str) -> str:
        return error.strip().lower()
