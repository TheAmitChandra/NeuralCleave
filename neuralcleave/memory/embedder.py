"""Local embedding model — lazy singleton backed by sentence-transformers.

Loads ``all-MiniLM-L6-v2`` (≈80 MB, Apache 2.0) on first call and caches
the model for the process lifetime.  The model runs entirely in-process on
CPU — no external API key, no network calls after the first download.

The public interface is async: :func:`encode` runs the CPU-bound encode step
in the default thread-pool executor so it never blocks the event loop.

Usage::

    from neuralcleave.memory.embedder import encode

    vector = await encode("how do I handle rate limit errors?")
    if vector is not None:
        ctx = await memory.retrieve(text, embedding=vector)

When ``sentence-transformers`` is not installed, :func:`encode` returns
``None`` and logs a one-time warning.  Callers must handle the ``None``
case — :meth:`MemoryRetrievalPipeline.retrieve` already skips semantic
search when ``embedding`` is ``None``.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer  # type: ignore[import]

logger = logging.getLogger(__name__)

_MODEL_NAME = "all-MiniLM-L6-v2"

_lock = threading.Lock()
_model: SentenceTransformer | None = None
_unavailable: bool = False


def _load_model() -> SentenceTransformer | None:
    """Load the embedding model (blocking). Thread-safe via module-level lock."""
    global _model, _unavailable

    with _lock:
        if _model is not None:
            return _model
        if _unavailable:
            return None

        try:
            from sentence_transformers import (
                SentenceTransformer,  # type: ignore[import]
            )

            _model = SentenceTransformer(_MODEL_NAME)
            logger.info("embedder: loaded %s (%d dims)", _MODEL_NAME, _model.get_sentence_embedding_dimension())
            return _model
        except ImportError:
            _unavailable = True
            logger.warning(
                "embedder: sentence-transformers not installed — semantic memory disabled. "
                "Run: pip install sentence-transformers"
            )
            return None
        except Exception as exc:
            _unavailable = True
            logger.warning("embedder: failed to load %s: %s — semantic memory disabled", _MODEL_NAME, exc)
            return None


async def encode(text: str) -> list[float] | None:
    """Return the embedding vector for *text*, or None if unavailable.

    The encode step runs in the thread-pool executor so the event loop is
    never blocked while the model computes.  The model is loaded once on
    first call and cached for all subsequent calls.
    """
    if not text or not text.strip():
        return None

    loop = asyncio.get_running_loop()
    try:
        vector = await loop.run_in_executor(None, _encode_sync, text)
        return vector
    except Exception as exc:
        logger.debug("embedder.encode failed: %s", exc)
        return None


def _encode_sync(text: str) -> list[float] | None:
    """Synchronous encode — must be called from a thread, not the event loop."""
    model = _load_model()
    if model is None:
        return None
    result = model.encode(text, normalize_embeddings=True)
    return result.tolist()


def dimensions() -> int | None:
    """Return the embedding dimension, or None if the model is not loaded."""
    model = _load_model()
    if model is None:
        return None
    return model.get_sentence_embedding_dimension()


def is_available() -> bool | None:
    """Report the embedder's current cached state without loading anything.

    Unlike ``dimensions()``, this never calls ``_load_model()`` — that can
    block on a multi-second-to-minutes model download on first use, which
    is fine for a one-off call but wrong for a frequently-polled status
    endpoint. Returns ``True`` once a model has successfully loaded,
    ``False`` once loading has been confirmed to fail (missing package or
    any other load error), or ``None`` if neither has happened yet (no
    embed call has been made since the process started).
    """
    if _model is not None:
        return True
    if _unavailable:
        return False
    return None
