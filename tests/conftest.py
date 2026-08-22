"""Pytest session setup, applied before any test module is imported.

Several module-level singletons resolve a persistent SQLite path from an
env var at *import* time. Without these overrides, simply importing the
owning module during test collection would create/write to the developer's
real ``~/.neuralcleave/`` state. Route them all to in-memory databases for
the whole test session instead.

- ``neuralcleave.privacy.audit.AUDIT_LOG`` -> ``NEURALCLEAVE_AUDIT_DB_PATH``
- ``neuralcleave.tools.approval_policy.POLICY`` -> ``NEURALCLEAVE_APPROVAL_DB_PATH``
- ``neuralcleave.skills.review.REVIEW_QUEUE`` -> ``NEURALCLEAVE_SKILL_REVIEW_DB_PATH``
- ``neuralcleave.plugins.state.STATE_STORE`` -> ``NEURALCLEAVE_PLUGIN_STATE_DB_PATH``
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("NEURALCLEAVE_AUDIT_DB_PATH", ":memory:")
os.environ.setdefault("NEURALCLEAVE_APPROVAL_DB_PATH", ":memory:")
os.environ.setdefault("NEURALCLEAVE_SKILL_REVIEW_DB_PATH", ":memory:")
os.environ.setdefault("NEURALCLEAVE_PLUGIN_STATE_DB_PATH", ":memory:")


@pytest.fixture(autouse=True)
def _embedder_unavailable_by_default():
    """Force neuralcleave.memory.embedder to report unavailable by default
    in every test, regardless of whether sentence-transformers actually
    happens to be installed in this environment.

    Before round 5's dependency fix (2026-08-21), sentence-transformers was
    never in a real dependency list, so `_embed()`/`encode()` always
    returned None everywhere it ran, including in every test. Dozens of
    pipeline tests build a `memory = MagicMock()` (or a hand-written fake)
    that never implements `store_semantic` as an async method — that
    branch (`if _embedding is not None: ... store_semantic(...)`) simply
    never ran, masking the gap. Now that the real package is a genuine
    dependency, whether that branch fires depends on whether it happens to
    be installed wherever tests run, which tests must not be sensitive to.
    This restores the deterministic "unavailable" default those tests were
    unknowingly relying on. Tests that specifically exercise the real
    encode()/_load_model() path (test_memory_embedder.py) explicitly set
    _model/_unavailable themselves and are unaffected; tests that replace
    `encode` outright (e.g. test_agent_pipeline.py's mock_embedder fixture)
    never reach _load_model()/_unavailable at all.
    """
    import neuralcleave.memory.embedder as emb

    orig_model, orig_unavailable = emb._model, emb._unavailable
    emb._model = None
    emb._unavailable = True
    yield
    emb._model, emb._unavailable = orig_model, orig_unavailable
