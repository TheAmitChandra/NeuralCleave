"""Unit tests for cortexflow.commands.handler — CommandHandler + CommandResult."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from cortexflow_ai.commands.handler import CommandHandler, CommandResult

# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------


class FakeSession:
    def __init__(self, session_id: str = "sess-abc123", channel: str = "telegram"):
        self.session_id = session_id
        self.channel = channel
        self.turn_count = 5
        self.idle_seconds = 42.0
        self._cleared = False

    def clear(self) -> None:
        self._cleared = True


class FakeRouter:
    privacy_mode = False
    auto_complexity = True
    _primary = "gemini-2.0-flash"


class FakeLongTerm:
    async def search(self, *, session_id, query, limit=5):
        if query == "nothing":
            return []
        return [
            {"content": f"memory about {query}", "importance_score": 0.9},
            {"content": "another result", "importance_score": 0.5},
        ]


# ---------------------------------------------------------------------------
# CommandResult dataclass
# ---------------------------------------------------------------------------


def test_command_result_defaults():
    r = CommandResult(text="hello")
    assert r.text == "hello"
    assert r.handled is True


def test_command_result_unhandled():
    r = CommandResult(text="", handled=False)
    assert r.handled is False


# ---------------------------------------------------------------------------
# is_command / parse
# ---------------------------------------------------------------------------


def test_is_command_with_slash():
    h = CommandHandler()
    assert h.is_command("/reset") is True


def test_is_command_without_slash():
    h = CommandHandler()
    assert h.is_command("hello world") is False


def test_is_command_empty_string():
    h = CommandHandler()
    assert h.is_command("") is False


def test_parse_simple_command():
    h = CommandHandler()
    name, args = h.parse("/reset")
    assert name == "reset"
    assert args == []


def test_parse_command_with_args():
    h = CommandHandler()
    name, args = h.parse("/memory ai tools search")
    assert name == "memory"
    assert args == ["ai", "tools", "search"]


def test_parse_normalises_case():
    h = CommandHandler()
    name, _ = h.parse("/RESET")
    assert name == "reset"


def test_parse_bare_slash_returns_empty_name():
    h = CommandHandler()
    name, args = h.parse("/")
    assert name == ""
    assert args == []


# ---------------------------------------------------------------------------
# register / registered_names
# ---------------------------------------------------------------------------


def test_register_and_lookup():
    h = CommandHandler()

    async def my_cmd(*args, **kwargs) -> str:
        return "ok"

    h.register("hello", my_cmd)
    assert "hello" in h.registered_names()


def test_registered_names_sorted():
    h = CommandHandler.make_default()
    names = h.registered_names()
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# dispatch — non-command passthrough
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_non_command_passthrough():
    h = CommandHandler()
    result = await h.dispatch("just a normal message")
    assert result.handled is False


# ---------------------------------------------------------------------------
# dispatch — unknown command
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatch_unknown_command():
    h = CommandHandler.make_default()
    result = await h.dispatch("/nonexistent")
    assert result.handled is True
    assert "Unknown command" in result.text
    assert "/nonexistent" in result.text


@pytest.mark.asyncio
async def test_dispatch_bare_slash_returns_usage():
    h = CommandHandler.make_default()
    result = await h.dispatch("/")
    assert result.handled is True
    assert "Usage: /command" in result.text


# ---------------------------------------------------------------------------
# /reset
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reset_clears_session():
    h = CommandHandler.make_default()
    session = FakeSession()
    result = await h.dispatch("/reset", session=session)
    assert result.handled is True
    assert session._cleared is True
    assert "cleared" in result.text.lower()


@pytest.mark.asyncio
async def test_reset_no_session():
    h = CommandHandler.make_default()
    result = await h.dispatch("/reset")
    assert result.handled is True
    assert "No active session" in result.text


# ---------------------------------------------------------------------------
# /memory
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_memory_with_results():
    h = CommandHandler.make_default()
    result = await h.dispatch(
        "/memory ai tools",
        session=FakeSession(),
        long_term=FakeLongTerm(),
    )
    assert result.handled is True
    assert "ai tools" in result.text


@pytest.mark.asyncio
async def test_memory_no_results():
    h = CommandHandler.make_default()
    result = await h.dispatch(
        "/memory nothing",
        session=FakeSession(),
        long_term=FakeLongTerm(),
    )
    assert "No memories" in result.text


@pytest.mark.asyncio
async def test_memory_no_long_term():
    h = CommandHandler.make_default()
    result = await h.dispatch("/memory hello")
    assert "not configured" in result.text.lower()


@pytest.mark.asyncio
async def test_memory_without_session_passes_none_session_id():
    """Regression: session_id must be None (cross-session), not '%' (literal match)."""
    received: dict = {}

    class CapturingLongTerm:
        async def search(self, *, session_id, query, limit=5):
            received["session_id"] = session_id
            return []

    h = CommandHandler.make_default()
    await h.dispatch("/memory something", long_term=CapturingLongTerm())
    assert received.get("session_id") is None


@pytest.mark.asyncio
async def test_memory_always_passes_none_session_id_for_cross_session_search():
    """Regression: /memory must search cross-session (session_id=None) even when
    a session is active. LTM entries are keyed by channel name, not session UUID,
    so filtering by UUID would return nothing."""
    received: dict = {}

    class CapturingLongTerm:
        async def search(self, *, session_id, query, limit=5):
            received["session_id"] = session_id
            return []

    h = CommandHandler.make_default()
    await h.dispatch("/memory something", session=FakeSession(session_id="real-sess-id"), long_term=CapturingLongTerm())
    assert received.get("session_id") is None


# ---------------------------------------------------------------------------
# /model
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_no_args_shows_current():
    h = CommandHandler.make_default()
    result = await h.dispatch("/model", router=FakeRouter())
    assert result.handled is True
    assert "Current model" in result.text


@pytest.mark.asyncio
async def test_model_with_name_acknowledges():
    h = CommandHandler.make_default()
    result = await h.dispatch("/model gpt-4o")
    assert "gpt-4o" in result.text


# ---------------------------------------------------------------------------
# /status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_status_with_session_and_router():
    h = CommandHandler.make_default()
    result = await h.dispatch(
        "/status",
        session=FakeSession(session_id="sess-abc123"),
        router=FakeRouter(),
    )
    assert result.handled is True
    assert "sess-abc" in result.text
    assert "Privacy" in result.text


@pytest.mark.asyncio
async def test_status_no_session():
    h = CommandHandler.make_default()
    result = await h.dispatch("/status")
    assert result.handled is True
    assert "none" in result.text.lower()


# ---------------------------------------------------------------------------
# /voice
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_voice_on():
    h = CommandHandler.make_default()
    result = await h.dispatch("/voice on")
    assert "enabled" in result.text.lower()


@pytest.mark.asyncio
async def test_voice_off():
    h = CommandHandler.make_default()
    result = await h.dispatch("/voice off")
    assert "disabled" in result.text.lower()


@pytest.mark.asyncio
async def test_voice_bad_arg():
    h = CommandHandler.make_default()
    result = await h.dispatch("/voice maybe")
    assert "Usage" in result.text


# ---------------------------------------------------------------------------
# /compact
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_no_session():
    h = CommandHandler.make_default()
    result = await h.dispatch("/compact", router=FakeRouter())
    assert "No active session" in result.text


@pytest.mark.asyncio
async def test_compact_no_router():
    h = CommandHandler.make_default()
    result = await h.dispatch("/compact", session=FakeSession())
    assert "Router not available" in result.text


@pytest.mark.asyncio
async def test_compact_success_truncates_long_summary():
    h = CommandHandler.make_default()
    long_summary = "x" * 250
    with patch(
        "cortexflow_ai.memory.compactor.ConversationCompactor.compact",
        new=AsyncMock(return_value=long_summary),
    ):
        result = await h.dispatch(
            "/compact", session=FakeSession(), router=FakeRouter(), long_term=FakeLongTerm(),
        )
    assert "Session compacted." in result.text
    assert "…" in result.text
    assert "x" * 200 in result.text
    assert "x" * 201 not in result.text


@pytest.mark.asyncio
async def test_compact_short_summary_not_truncated():
    h = CommandHandler.make_default()
    with patch(
        "cortexflow_ai.memory.compactor.ConversationCompactor.compact",
        new=AsyncMock(return_value="Short summary."),
    ):
        result = await h.dispatch("/compact", session=FakeSession(), router=FakeRouter())
    assert "Short summary." in result.text
    assert "…" not in result.text


@pytest.mark.asyncio
async def test_compact_empty_summary_reports_nothing_to_compact():
    h = CommandHandler.make_default()
    with patch(
        "cortexflow_ai.memory.compactor.ConversationCompactor.compact",
        new=AsyncMock(return_value=""),
    ):
        result = await h.dispatch("/compact", session=FakeSession(), router=FakeRouter())
    assert "Nothing to compact" in result.text
