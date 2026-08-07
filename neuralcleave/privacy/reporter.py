"""Format PrivacyAuditLog entries into human-readable and machine-readable reports.

Usage::

    from neuralcleave.privacy.audit import AUDIT_LOG
    from neuralcleave.privacy.reporter import format_text_report, format_json_report

    text = format_text_report(AUDIT_LOG.entries_for_session("my-session"))
    data = format_json_report(AUDIT_LOG.entries_for_session("my-session"))
"""

from __future__ import annotations

import datetime
from typing import Any

from neuralcleave.privacy.audit import AuditEntry


def format_text_report(
    entries: list[AuditEntry],
    session_id: str | None = None,
) -> str:
    """Return a plain-text privacy report for *entries*.

    Suitable for the ``neuralcleave privacy report`` CLI command.
    """
    header = "NeuralCleave Privacy Report"
    if session_id:
        header += f" — session {session_id}"
    lines: list[str] = [header, "=" * len(header), ""]

    if not entries:
        lines.append("No outbound HTTP calls recorded.")
        return "\n".join(lines)

    # Unique destinations first
    seen: dict[str, None] = {}
    for e in entries:
        seen[e.destination] = None
    destinations = list(seen)

    lines.append(f"Destinations contacted: {len(destinations)}")
    for dest in destinations:
        lines.append(f"  • {dest}")
    lines.append("")

    lines.append(f"Total calls: {len(entries)}")
    lines.append("")

    for entry in entries:
        ts = datetime.datetime.fromtimestamp(entry.timestamp).strftime("%H:%M:%S")
        lines.append(f"  [{ts}] {entry.method} {entry.url}")

    return "\n".join(lines)


def format_json_report(
    entries: list[AuditEntry],
    session_id: str | None = None,
) -> dict[str, Any]:
    """Return a JSON-serialisable dict for the privacy report API endpoint."""
    seen: dict[str, None] = {}
    for e in entries:
        seen[e.destination] = None

    return {
        "session_id": session_id,
        "total": len(entries),
        "unique_destinations": list(seen),
        "entries": [e.to_dict() for e in entries],
    }
