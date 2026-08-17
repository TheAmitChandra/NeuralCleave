"""Pytest session setup, applied before any test module is imported.

``neuralcleave.privacy.audit.AUDIT_LOG`` is a module-level singleton that
resolves its persistent SQLite path from ``NEURALCLEAVE_AUDIT_DB_PATH`` at
*import* time. Without this override, simply importing any neuralcleave
module during test collection would create/write to the developer's real
``~/.neuralcleave/privacy_audit.db``. Route it to an in-memory database for
the whole test session instead.
"""

from __future__ import annotations

import os

os.environ.setdefault("NEURALCLEAVE_AUDIT_DB_PATH", ":memory:")
