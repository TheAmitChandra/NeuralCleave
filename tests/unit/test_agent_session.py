"""Unit tests for NeuralCleave.agent.session."""

from __future__ import annotations

import time

from neuralcleave.agent.session import Session, SessionManager, Turn

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


def test_session_build_prompt_system_role_labeled_correctly() -> None:
    """Regression: system turns (injected after compaction) must appear as
    'System:' not 'Assistant:' so the LLM understands the turn is contextual
    framing, not a prior response it generated."""
    s = Session("telegram", "u1")
    s.add_turn("system", "[Previous conversation summary]\nWe discussed Python.")
    s.add_turn("user", "Continue from there.")
    prompt = s.build_prompt()
    assert "System: [Previous conversation summary]" in prompt
    assert "Assistant: [Previous conversation summary]" not in prompt
    assert "User: Continue from there." in prompt


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


def test_session_manager_get_by_id_finds_session() -> None:
    mgr = SessionManager()
    s = mgr.get_or_create("telegram", "u1")
    assert mgr.get_by_id(s.session_id) is s


def test_session_manager_get_by_id_unknown_returns_none() -> None:
    mgr = SessionManager()
    mgr.get_or_create("telegram", "u1")
    assert mgr.get_by_id("nonexistent") is None


def test_session_manager_get_by_id_distinguishes_sessions() -> None:
    mgr = SessionManager()
    s1 = mgr.get_or_create("telegram", "u1")
    s2 = mgr.get_or_create("discord", "u2")
    assert mgr.get_by_id(s1.session_id) is s1
    assert mgr.get_by_id(s2.session_id) is s2


def test_session_manager_gc_removes_idle() -> None:
    mgr = SessionManager(idle_timeout=-1.0)  # negative → all sessions always "idle"
    mgr.get_or_create("telegram", "u1")
    mgr.get_or_create("discord", "u2")
    assert mgr.active_count == 2
    removed = mgr.gc()
    assert removed == 2
    assert mgr.active_count == 0


# ---------------------------------------------------------------------------
# session_id stability across Session recreation (round-6 gap analysis P2,
# 2026-08-30) — this is the identity long-term memory writes/searches/forget
# are scoped by (agent/runtime.py, agent/pipeline.py), so it must survive a
# GC'd idle session or a gateway restart for the same real user, not mint a
# fresh, unrelated identity every time.
# ---------------------------------------------------------------------------


def test_session_id_is_derived_from_channel_and_sender() -> None:
    s = Session("telegram", "u1")
    assert s.session_id == "telegram:u1"


def test_session_id_is_stable_across_recreation_for_the_same_sender() -> None:
    """A GC'd-then-recreated Session for the same real user must reuse the
    same session_id, or every prior long-term memory entry becomes
    unreachable to /forget, /tags, and retrieval."""
    first = Session("telegram", "u1")
    second = Session("telegram", "u1")  # simulates recreation after GC/restart
    assert first.session_id == second.session_id


def test_session_manager_recreates_same_session_id_after_gc() -> None:
    mgr = SessionManager(idle_timeout=-1.0)
    original = mgr.get_or_create("telegram", "u1")
    mgr.gc()
    assert mgr.get("telegram", "u1") is None  # really was removed, not reused
    recreated = mgr.get_or_create("telegram", "u1")
    assert recreated is not original
    assert recreated.session_id == original.session_id


def test_session_id_differs_across_senders_and_channels() -> None:
    assert Session("telegram", "u1").session_id != Session("telegram", "u2").session_id
    assert Session("telegram", "u1").session_id != Session("discord", "u1").session_id
