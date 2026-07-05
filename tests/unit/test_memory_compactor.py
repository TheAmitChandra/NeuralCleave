"""Unit tests for cortexflow.memory.compactor — ConversationCompactor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from cortexflow_ai.memory.compactor import (
    _CHARS_PER_TOKEN,
    _DEFAULT_CONTEXT_TOKENS,
    _SUMMARY_IMPORTANCE,
    ConversationCompactor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(turns: list[tuple[str, str]] | None = None) -> MagicMock:
    """Build a minimal mock Session."""
    session = MagicMock()
    session.session_id = "test-session"
    session.turn_count = 0

    history = [{"role": r, "content": c} for r, c in (turns or [])]
    # history_as_dicts() is what the compactor actually calls
    session.history_as_dicts = MagicMock(return_value=history)

    def _clear():
        history.clear()
        session.turn_count = 0

    def _add_turn(role, content, **_):
        history.append({"role": role, "content": content})
        session.turn_count += 1
        session.history_as_dicts.return_value = list(history)

    session.clear = MagicMock(side_effect=_clear)
    session.add_turn = MagicMock(side_effect=_add_turn)
    return session


def _make_router(summary_text: str = "Summary text.") -> MagicMock:
    router = MagicMock()
    result = MagicMock()
    result.text = summary_text
    router.generate = AsyncMock(return_value=result)
    return router


def _make_long_term() -> MagicMock:
    lt = MagicMock()
    lt.init_schema = AsyncMock()
    lt.store = AsyncMock(return_value=1)
    return lt


# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------


def test_estimated_tokens_empty_session():
    session = _make_session()
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())
    assert c.estimated_tokens == 0


def test_estimated_tokens_with_content():
    content = "x" * 400  # 100 tokens
    session = _make_session([("user", content)])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())
    assert c.estimated_tokens == 100


def test_fill_fraction_empty():
    session = _make_session()
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())
    assert c.fill_fraction == 0.0


def test_fill_fraction_half_full():
    # Fill half the default context
    half_chars = (_DEFAULT_CONTEXT_TOKENS // 2) * _CHARS_PER_TOKEN
    session = _make_session([("user", "x" * half_chars)])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())
    assert c.fill_fraction == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# compact()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_returns_summary():
    session = _make_session([("user", "Hello"), ("assistant", "Hi there!")])
    router = _make_router("This is the summary.")
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=router)

    summary = await c.compact()
    assert summary == "This is the summary."


@pytest.mark.asyncio
async def test_compact_clears_session_history():
    session = _make_session([("user", "Turn 1"), ("assistant", "Reply 1")])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router("Summary"))

    await c.compact()
    session.clear.assert_called_once()


@pytest.mark.asyncio
async def test_compact_adds_summary_turn():
    session = _make_session([("user", "x")])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router("The summary"))

    await c.compact()
    # add_turn should be called with "system" role
    session.add_turn.assert_called_once()
    role, content = session.add_turn.call_args[0]
    assert role == "system"
    assert "The summary" in content


@pytest.mark.asyncio
async def test_compact_stores_to_long_term():
    session = _make_session([("user", "Hello")])
    lt = _make_long_term()
    c = ConversationCompactor(session=session, long_term=lt, router=_make_router("Summary"))

    await c.compact()
    lt.store.assert_called_once()
    call_kwargs = lt.store.call_args[1]
    assert call_kwargs["session_id"] == "test-session"
    assert call_kwargs["memory_type"] == "summary"
    assert call_kwargs["importance"] == _SUMMARY_IMPORTANCE


@pytest.mark.asyncio
async def test_compact_persist_failure_still_returns_summary():
    session = _make_session([("user", "Hello")])
    lt = _make_long_term()
    lt.store = AsyncMock(side_effect=RuntimeError("db locked"))
    c = ConversationCompactor(session=session, long_term=lt, router=_make_router("The summary"))

    summary = await c.compact()

    assert summary == "The summary"
    session.clear.assert_called_once()  # history still replaced despite persist failure


@pytest.mark.asyncio
async def test_compact_empty_history_returns_empty():
    session = _make_session()
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())

    summary = await c.compact()
    assert summary == ""
    session.clear.assert_not_called()


@pytest.mark.asyncio
async def test_compact_router_failure_returns_empty():
    session = _make_session([("user", "Hello")])
    router = MagicMock()
    router.generate = AsyncMock(side_effect=RuntimeError("router down"))
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=router)

    summary = await c.compact()
    assert summary == ""


# ---------------------------------------------------------------------------
# maybe_compact()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_maybe_compact_below_threshold_returns_false():
    session = _make_session([("user", "short")])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router())

    result = await c.maybe_compact(threshold=0.9)
    assert result is False


@pytest.mark.asyncio
async def test_maybe_compact_above_threshold_returns_true():
    # Fill 60% of context
    chars = int(_DEFAULT_CONTEXT_TOKENS * 0.6) * _CHARS_PER_TOKEN
    session = _make_session([("user", "x" * chars)])
    c = ConversationCompactor(session=session, long_term=_make_long_term(), router=_make_router("Summary"))

    result = await c.maybe_compact(threshold=0.5)
    assert result is True


@pytest.mark.asyncio
async def test_maybe_compact_calls_compact_when_triggered():
    chars = int(_DEFAULT_CONTEXT_TOKENS * 0.8) * _CHARS_PER_TOKEN
    session = _make_session([("user", "x" * chars)])
    lt = _make_long_term()
    c = ConversationCompactor(session=session, long_term=lt, router=_make_router("Summary"))

    await c.maybe_compact(threshold=0.5)
    lt.store.assert_called_once()  # compact was called


# ---------------------------------------------------------------------------
# Regression: compactor must work with a real Session (not just mocks)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_with_real_session_does_not_raise() -> None:
    """Regression: _build_history_text and _estimate_tokens called history_as_dicts()
    (with parens). Using a real Session confirms the fix — a broken call to
    .history (method object) would raise TypeError here."""
    from cortexflow_ai.agent.session import Session

    session = Session(channel="test", sender_id="u1")
    session.add_turn("user", "What is asyncio?")
    session.add_turn("assistant", "It's Python's async framework.")

    lt = _make_long_term()
    router = _make_router("Asyncio discussion summary.")
    c = ConversationCompactor(session=session, long_term=lt, router=router)

    summary = await c.compact()
    assert summary == "Asyncio discussion summary."
    # After compact, session history is replaced with a single system summary turn
    assert session.turn_count == 1
    assert session.history()[0].role == "system"


def test_estimated_tokens_with_real_session() -> None:
    """Regression: _estimate_tokens must use history_as_dicts(), not .history."""
    from cortexflow_ai.agent.session import Session

    session = Session(channel="test", sender_id="u1")
    session.add_turn("user", "x" * 400)  # 100 tokens

    lt = _make_long_term()
    c = ConversationCompactor(session=session, long_term=lt, router=_make_router())
    assert c.estimated_tokens == 100
