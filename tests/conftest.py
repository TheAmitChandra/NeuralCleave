"""Pytest session setup, applied before any test module is imported.

Several module-level singletons resolve a persistent SQLite path from an
env var at *import* time. Without these overrides, simply importing the
owning module during test collection would create/write to the developer's
real ``~/.neuralcleave/`` state. Route them all to in-memory databases for
the whole test session instead.

- ``neuralcleave.privacy.audit.AUDIT_LOG`` -> ``NEURALCLEAVE_AUDIT_DB_PATH``
- ``neuralcleave.tools.approval_policy.POLICY`` -> ``NEURALCLEAVE_APPROVAL_DB_PATH``
- ``neuralcleave.skills.review.REVIEW_QUEUE`` -> ``NEURALCLEAVE_SKILL_REVIEW_DB_PATH``
"""

from __future__ import annotations

import os

os.environ.setdefault("NEURALCLEAVE_AUDIT_DB_PATH", ":memory:")
os.environ.setdefault("NEURALCLEAVE_APPROVAL_DB_PATH", ":memory:")
os.environ.setdefault("NEURALCLEAVE_SKILL_REVIEW_DB_PATH", ":memory:")
