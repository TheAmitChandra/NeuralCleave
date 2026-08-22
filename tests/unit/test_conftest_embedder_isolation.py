"""Regression guard for the autouse embedder-isolation fixture in
tests/conftest.py (round 5 gap analysis P0 follow-up, 2026-08-21).

Before this fixture existed, whether neuralcleave.memory.embedder.encode()
returned a real vector or None during a test depended on whether
sentence-transformers happened to be installed in the environment - once
it became a real dependency, that flipped dozens of pipeline tests' silent
assumption that `_embedding is not None` never fires, breaking test
doubles that never implemented `store_semantic` as an async method.
"""

from __future__ import annotations

import pytest

import neuralcleave.memory.embedder as emb


@pytest.mark.asyncio
async def test_encode_is_unavailable_by_default_regardless_of_environment():
    assert emb._unavailable is True
    assert emb._model is None
    assert await emb.encode("hello") is None


def test_is_available_reports_false_by_default():
    assert emb.is_available() is False


class TestFixtureIsolationAcrossTests:
    """Ordered pair: the first test simulates a real model having loaded
    (as CI would produce with sentence-transformers actually installed);
    the second proves that state doesn't leak into a following test."""

    def test_1_simulate_a_real_model_having_loaded(self):
        emb._model = object()
        emb._unavailable = False
        assert emb._model is not None  # sanity: simulation took effect

    def test_2_next_test_still_starts_unavailable(self):
        assert emb._model is None
        assert emb._unavailable is True
