"""Unit tests for cortexflow.memory.archiver — SessionArchiver."""

from __future__ import annotations

import sqlite3

import pytest

from cortexflow_ai.memory.archiver import SessionArchiver
from cortexflow_ai.memory.long_term import LongTermMemory


class _FakeResult:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeRouter:
    """Stub ModelRouter — returns a fixed summary without any network calls."""

    def __init__(self, summary: str = "User likes Python and works on CortexFlow.") -> None:
        self.summary = summary
        self.prompts: list[str] = []

    async def generate(self, prompt: str, task_type: str | None = None):
        self.prompts.append(prompt)
        return _FakeResult(self.summary)


class _FailingRouter:
    async def generate(self, prompt: str, task_type: str | None = None):
        raise RuntimeError("no API key configured")


@pytest.fixture()
async def lt(tmp_path):
    db_path = str(tmp_path / "archive_test.db")
    store = LongTermMemory(db_path=db_path)
    await store.init_schema()
    return store


def _backdate(db_path: str, session_id: str, days_ago: int) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE memory_entries SET last_accessed_at = datetime('now', '-{days_ago} days') "  # noqa: S608
        "WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# archive_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_session_returns_none_for_empty_session(lt):
    archiver = SessionArchiver(long_term=lt, router=_FakeRouter())
    result = await archiver.archive_session("nonexistent")
    assert result is None


@pytest.mark.asyncio
async def test_archive_session_replaces_entries_with_summary(lt):
    await lt.store("s1", "User likes Python", importance=0.6)
    await lt.store("s1", "User works on CortexFlow project", importance=0.6)
    router = _FakeRouter("Condensed summary text.")

    summary = await archiver_for(lt, router).archive_session("s1")

    assert summary == "Condensed summary text."
    rows = await lt.get_by_session("s1")
    assert len(rows) == 1
    assert rows[0]["memory_type"] == "archive_summary"
    assert "archive" in rows[0]["tags"]
    assert "Condensed summary text." in rows[0]["content"]


@pytest.mark.asyncio
async def test_archive_session_leaves_other_sessions_untouched(lt):
    await lt.store("s1", "session one content", importance=0.5)
    await lt.store("s2", "session two content", importance=0.5)

    await archiver_for(lt, _FakeRouter()).archive_session("s1")

    rows_s2 = await lt.get_by_session("s2")
    assert len(rows_s2) == 1
    assert rows_s2[0]["content"] == "session two content"


@pytest.mark.asyncio
async def test_archive_session_returns_none_when_router_fails(lt):
    await lt.store("s1", "some content", importance=0.5)

    summary = await archiver_for(lt, _FailingRouter()).archive_session("s1")

    assert summary is None
    # Original entry must survive an aborted archive attempt.
    rows = await lt.get_by_session("s1")
    assert len(rows) == 1
    assert rows[0]["content"] == "some content"


# ---------------------------------------------------------------------------
# archive_inactive_sessions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_inactive_sessions_only_archives_stale(lt):
    await lt.store("fresh", "recent content", importance=0.5)
    await lt.store("stale", "old content", importance=0.5)
    _backdate(lt._db_path, "stale", days_ago=60)

    archived = await archiver_for(lt, _FakeRouter()).archive_inactive_sessions(older_than_days=30)

    assert list(archived.keys()) == ["stale"]
    fresh_rows = await lt.get_by_session("fresh")
    assert fresh_rows[0]["content"] == "recent content"


@pytest.mark.asyncio
async def test_archive_inactive_sessions_no_stale_sessions_returns_empty(lt):
    await lt.store("fresh", "recent content", importance=0.5)
    archived = await archiver_for(lt, _FakeRouter()).archive_inactive_sessions(older_than_days=30)
    assert archived == {}


def archiver_for(lt: LongTermMemory, router: object) -> SessionArchiver:
    return SessionArchiver(long_term=lt, router=router)  # type: ignore[arg-type]
