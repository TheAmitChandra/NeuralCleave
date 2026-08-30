"""Lightweight append-only audit log for the embedded desktop terminal.

Unlike ``neuralcleave.privacy.audit.PrivacyAuditLog``, which is scoped to
outbound HTTP calls (method/url/destination), a raw shell command typed
into ``gateway/terminal.py`` doesn't fit that schema — this is a separate,
much simpler, purpose-built log: one JSON line per command, timestamp plus
the exact text run.

Round 7 gap analysis P4 (2026-08-30): terminal.py commands were the one
category of shell execution in the codebase with no trace of ever having
run. Agent-issued ``ShellTool`` calls go through ``ApprovalQueue`` when
``security.require_shell_approval`` is enabled — but the embedded terminal
is a direct interactive session for the operator's own machine, and
deliberately does *not* gate on approval the way ``ShellTool`` does
(prompting for approval on every keystroke of your own terminal session
would defeat the point of having one). It should still leave a record.
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LOG_PATH = os.getenv("NEURALCLEAVE_TERMINAL_LOG_PATH") or "~/.neuralcleave/terminal_history.log"


def _log_path() -> Path:
    return Path(DEFAULT_LOG_PATH).expanduser()


def record_command(cmd: str) -> None:
    """Append one JSON-line entry recording *cmd*.

    Best-effort: a logging failure (disk full, permissions) must never
    break the terminal itself, so any exception is caught and logged
    rather than propagated.
    """
    entry = {"timestamp": time.time(), "cmd": cmd}
    try:
        path = _log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception as exc:
        logger.warning("terminal_audit: failed to record command (%s)", exc)
