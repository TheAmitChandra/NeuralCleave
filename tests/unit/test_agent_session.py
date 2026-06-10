"""Unit tests for cortexflow.agent.session."""

from __future__ import annotations

import time

from cortexflow.agent.session import Session, SessionManager, Turn

# ---------------------------------------------------------------------------
# Turn
# ---------------------------------------------------------------------------


def test_turn_to_dict() -> None:
    t = Turn(role="user", content="hello", timestamp=0.0)
    d = t.to_dict()
    assert d["role"] == "user"
    assert d["content"] == "hello"
    assert d["model"] is None


def test_turn_assistant_with_model() -> None:
    t = Turn(role="assistant", content="hi", model="gemini-flash")
    assert t.to_dict()["model"] == "gemini-flash"


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


def test_session_initial_state() -> None:
    s = Session("telegram", "u123")
    assert s.channel == "telegram"
    assert s.sender_id == "u123"
    assert s.turn_count == 0
    assert s.is_fresh is True
    assert s.history() == []


def test_session_add_turn_increments_count() -> None:
    s = Session("discord", "u1")
    s.add_turn("user", "hi")
    assert s.turn_count == 1
    assert not s.is_fresh


def test_session_rolling_window() -> None:
    s = Session("telegram", "u1", max_turns=4)
    for i in range(6):
        s.add_turn("user", f"msg {i}")
    history = s.history()
    assert len(history) == 4
    assert history[0].content == "msg 2"  # oldest in window


def test_session_clear_resets_history() -> None:
    s = Session("telegram", "u1")
    s.add_turn("user", "hello")
    s.add_turn("assistant", "world")
    s.clear()
    assert s.history() == []
    assert s.turn_count == 0
    assert s.is_fresh


def test_session_build_prompt_empty() -> None:
    s = Session("telegram", "u1")
    assert s.build_prompt() == ""


def test_session_build_prompt_with_turns() -> None:
    s = Session("telegram", "u1")
    s.add_turn("user", "What time is it?")
    s.add_turn("assistant", "It's noon.")
    prompt = s.build_prompt()
    assert "User: What time is it?" in prompt
    assert "Assistant: It's noon." in prompt


def test_session_build_prompt_include_turns_limit() -> None:
    s = Session("telegram", "u1")
    for i in range(10):
        s.add_turn("user", f"msg{i}")
    prompt = s.build_prompt(include_turns=2)
    assert "msg8" in prompt
    assert "msg9" in prompt
    assert "msg0" not in prompt


def test_session_history_as_dicts() -> None:
    s = Session("telegram", "u1")
    s.add_turn("user", "hello")
    dicts = s.history_as_dicts()
    assert len(dicts) == 1
    assert dicts[0]["role"] == "user"


def test_session_idle_seconds_increases() -> None:
    s = Session("telegram", "u1")
    idle1 = s.idle_seconds
    time.sleep(0.01)
    idle2 = s.idle_seconds
    assert idle2 > idle1


def test_session_repr_contains_channel() -> None:
    s = Session("slack", "u999")
    assert "slack" in repr(s)


# ---------------------------------------------------------------------------
# SessionManager
# ---------------------------------------------------------------------------


def test_session_manager_get_or_create() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create("telegram", "u1")
    s2 = mgr.get_or_create("telegram", "u1")
    assert s1 is s2  # same object returned


def test_session_manager_different_senders() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create("telegram", "u1")
    s2 = mgr.get_or_create("telegram", "u2")
    assert s1 is not s2


def test_session_manager_different_channels() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create("telegram", "u1")
    s2 = mgr.get_or_create("discord", "u1")
    assert s1 is not s2


def test_session_manager_remove() -> None:
    mgr = SessionManager()
    mgr.get_or_create("telegram", "u1")
    assert mgr.active_count == 1
    mgr.remove("telegram", "u1")
    assert mgr.active_count == 0
    assert mgr.get("telegram", "u1") is None


def test_session_manager_gc_removes_idle() -> None:
    mgr = SessionManager(idle_timeout=-1.0)  # negative → all sessions always "idle"
    mgr.get_or_create("telegram", "u1")
    mgr.get_or_create("discord", "u2")
    assert mgr.active_count == 2
    removed = mgr.gc()
    assert removed == 2
    assert mgr.active_count == 0
