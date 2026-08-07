"""Tests for the lazy-load embedding singleton."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_embedder_globals():
    """Reset module-level singletons between tests."""
    import neuralcleave.memory.embedder as emb

    orig_model = emb._model
    orig_unavailable = emb._unavailable
    yield
    emb._model = orig_model
    emb._unavailable = orig_unavailable


class TestEncodeAvailable:
    """encode() when sentence-transformers is present."""

    @pytest.mark.asyncio
    async def test_encode_returns_list_of_floats(self):
        fake_model = MagicMock()
        fake_model.encode.return_value = MagicMock(tolist=lambda: [0.1, 0.2, 0.3])
        fake_model.get_sentence_embedding_dimension.return_value = 3

        import neuralcleave.memory.embedder as emb

        emb._model = fake_model
        emb._unavailable = False

        result = await emb.encode("hello world")
        assert isinstance(result, list)
        assert result == [0.1, 0.2, 0.3]

    @pytest.mark.asyncio
    async def test_encode_empty_string_returns_none(self):
        from neuralcleave.memory.embedder import encode

        result = await encode("")
        assert result is None

    @pytest.mark.asyncio
    async def test_encode_whitespace_only_returns_none(self):
        from neuralcleave.memory.embedder import encode

        result = await encode("   ")
        assert result is None

    @pytest.mark.asyncio
    async def test_encode_calls_model_with_normalize(self):
        fake_model = MagicMock()
        fake_model.encode.return_value = MagicMock(tolist=lambda: [0.5])
        fake_model.get_sentence_embedding_dimension.return_value = 1

        import neuralcleave.memory.embedder as emb

        emb._model = fake_model
        emb._unavailable = False

        await emb.encode("test text")
        fake_model.encode.assert_called_once_with("test text", normalize_embeddings=True)


class TestEncodeUnavailable:
    """encode() when sentence-transformers is absent."""

    @pytest.mark.asyncio
    async def test_encode_returns_none_when_unavailable_flag_set(self):
        import neuralcleave.memory.embedder as emb

        emb._model = None
        emb._unavailable = True

        result = await emb.encode("hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_encode_returns_none_on_import_error(self):
        import neuralcleave.memory.embedder as emb

        emb._model = None
        emb._unavailable = False

        with patch("neuralcleave.memory.embedder._load_model", return_value=None):
            result = await emb.encode("hello")
        assert result is None


class TestDimensions:
    """dimensions() returns the model's output size."""

    def test_dimensions_returns_int_when_model_loaded(self):
        fake_model = MagicMock()
        fake_model.get_sentence_embedding_dimension.return_value = 384

        import neuralcleave.memory.embedder as emb

        emb._model = fake_model
        emb._unavailable = False

        assert emb.dimensions() == 384

    def test_dimensions_returns_none_when_unavailable(self):
        import neuralcleave.memory.embedder as emb

        emb._model = None
        emb._unavailable = True

        assert emb.dimensions() is None
