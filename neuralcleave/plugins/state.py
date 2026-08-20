"""Persistent enable/disable state for installed plugins.

P9 of the 2026-08-17 gap analysis: ``PluginRegistry`` previously only
discovered plugins already ``pip install``-ed via entry points, with no way
to install/enable/disable them from the CLI, and no persisted state — a
plugin was either present (and always loaded) or absent. This adds a
durable enabled/disabled flag, consulted by ``PluginRegistry.load_all()`` so
a disabled plugin stays discovered (visible in ``plugins list``) but never
actually loads its tools.

Mirrors the SQLite persistence pattern in ``neuralcleave/tools/approval_policy.py``.
Default db_path: ``~/.neuralcleave/plugin_state.db`` (override via
``NEURALCLEAVE_PLUGIN_STATE_DB_PATH``).
"""

from __future__ import annotations

import os
import sqlite3

DEFAULT_DB_PATH = os.getenv("NEURALCLEAVE_PLUGIN_STATE_DB_PATH") or "~/.neuralcleave/plugin_state.db"

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS plugin_state (
    name    TEXT    PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1
);
"""


class PluginStateStore:
    """Tracks which plugins are enabled/disabled, independent of whether
    they're discoverable via entry points.

    A plugin with no explicit record is enabled by default — this store
    only needs to persist the *exceptions* (plugins someone disabled).

    Args:
        db_path: SQLite database path (``~`` expanded), or ``None`` for
            in-memory-only behaviour (what tests get by default).
    """

    def __init__(self, db_path: str | None = DEFAULT_DB_PATH) -> None:
        self._state: dict[str, bool] = {}
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
        cursor = self._db.execute("SELECT name, enabled FROM plugin_state")
        for name, enabled in cursor.fetchall():
            self._state[name] = bool(enabled)

    def is_enabled(self, name: str) -> bool:
        """Whether *name* is enabled. Defaults to ``True`` (no record = enabled)."""
        return self._state.get(name, True)

    def set_enabled(self, name: str, enabled: bool) -> None:
        self._state[name] = enabled
        if self._db is not None:
            self._db.execute(
                "INSERT INTO plugin_state (name, enabled) VALUES (?, ?) "
                "ON CONFLICT(name) DO UPDATE SET enabled = excluded.enabled",
                (name, int(enabled)),
            )
            self._db.commit()

    def list_disabled(self) -> list[str]:
        return sorted(name for name, enabled in self._state.items() if not enabled)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


STATE_STORE: PluginStateStore = PluginStateStore()
