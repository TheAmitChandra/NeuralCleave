"""Unit tests for cortexflow.memory.long_term — LongTermMemory SQLite CRUD."""

from __future__ import annotations

import pytest

from cortexflow_ai.memory.long_term import LongTermMemory


@pytest.fixture()
async def lt(tmp_path):
    db_path = str(tmp_path / "test_memory.db")
    store = LongTermMemory(db_path=db_path)
    await store.init_schema()
    return store


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_schema_creates_db(tmp_path):
    db_path = str(tmp_path / "fresh.db")
    lt = LongTermMemory(db_path=db_path)
    await lt.init_schema()
    import os
    assert os.path.exists(db_path)


@pytest.mark.asyncio
async def test_init_schema_idempotent(tmp_path):
    db_path = str(tmp_path / "idem.db")
    lt = LongTermMemory(db_path=db_path)
    await lt.init_schema()
    await lt.init_schema()  # should not raise


@pytest.mark.asyncio
async def test_init_schema_migrates_pre_tags_database(tmp_path):
    import aiosqlite

    db_path = str(tmp_path / "legacy.db")
    # Simulate a database created before the `tags` column existed.
    async with aiosqlite.connect(db_path) as db:
        await db.executescript("""
            CREATE TABLE memory_entries (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id       TEXT    NOT NULL,
                content          TEXT    NOT NULL,
                importance_score REAL    NOT NULL DEFAULT 0.5,
                memory_type      TEXT    NOT NULL DEFAULT 'general',
                created_at       TEXT    NOT NULL,
                last_accessed_at TEXT    NOT NULL
            );
        """)
        await db.commit()

    lt = LongTermMemory(db_path=db_path)
    await lt.init_schema()  # must migrate, not raise

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("PRAGMA table_info(memory_entries)") as cursor:
            columns = {row[1] async for row in cursor}
    assert "tags" in columns


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_returns_positive_id(lt):
    row_id = await lt.store(session_id="s1", content="remember this", importance=0.8)
    assert row_id > 0


@pytest.mark.asyncio
async def test_store_multiple_returns_increasing_ids(lt):
    id1 = await lt.store("s1", "first", 0.5)
    id2 = await lt.store("s1", "second", 0.6)
    assert id2 > id1


@pytest.mark.asyncio
async def test_store_default_importance(lt):
    await lt.store("s1", "no importance given")
    rows = await lt.get_by_session("s1")
    assert rows[0]["importance_score"] == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_finds_matching_content(lt):
    await lt.store("s1", "Python asyncio tutorial", importance=0.7)
    await lt.store("s1", "JavaScript promises guide", importance=0.5)
    results = await lt.search(session_id="s1", query="asyncio")
    assert len(results) == 1
    assert "asyncio" in results[0]["content"]


@pytest.mark.asyncio
async def test_search_no_match_returns_empty(lt):
    await lt.store("s1", "some content", importance=0.5)
    results = await lt.search(session_id="s1", query="xyzzy_no_match")
    assert results == []


@pytest.mark.asyncio
async def test_search_respects_limit(lt):
    for i in range(10):
        await lt.store("s1", f"match content {i}", importance=0.5)
    results = await lt.search(session_id="s1", query="match", limit=3)
    assert len(results) <= 3


@pytest.mark.asyncio
async def test_search_session_id_none_searches_all_sessions(lt):
    await lt.store("session-A", "shared keyword alpha", importance=0.5)
    await lt.store("session-B", "shared keyword beta", importance=0.5)
    results = await lt.search(session_id=None, query="shared keyword")
    assert len(results) == 2


@pytest.mark.asyncio
async def test_search_explicit_session_still_scopes(lt):
    await lt.store("session-A", "shared keyword alpha", importance=0.5)
    await lt.store("session-B", "shared keyword beta", importance=0.5)
    results = await lt.search(session_id="session-A", query="shared keyword")
    assert len(results) == 1
    assert results[0]["session_id"] == "session-A"


@pytest.mark.asyncio
async def test_search_ordered_by_importance(lt):
    await lt.store("s1", "match low", importance=0.2)
    await lt.store("s1", "match high", importance=0.9)
    results = await lt.search(session_id="s1", query="match")
    assert results[0]["importance_score"] >= results[-1]["importance_score"]


@pytest.mark.asyncio
async def test_search_empty_query_returns_all_entries_for_session(lt):
    """Empty query must list all entries — not just rows containing '%%'."""
    await lt.store("s1", "first entry", importance=0.5)
    await lt.store("s1", "second entry", importance=0.6)
    await lt.store("other-session", "irrelevant", importance=0.5)
    results = await lt.search(session_id="s1", query="")
    assert len(results) == 2
    assert all(r["session_id"] == "s1" for r in results)


@pytest.mark.asyncio
async def test_search_empty_query_session_none_returns_all_sessions(lt):
    """Empty query with session_id=None must return entries from all sessions."""
    await lt.store("s1", "entry-a", importance=0.5)
    await lt.store("s2", "entry-b", importance=0.5)
    results = await lt.search(session_id=None, query="")
    assert len(results) == 2


# ---------------------------------------------------------------------------
# get_by_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_by_session_returns_own_entries(lt):
    await lt.store("session-A", "A content", 0.5)
    await lt.store("session-B", "B content", 0.5)
    rows = await lt.get_by_session("session-A")
    assert all(r["session_id"] == "session-A" for r in rows)
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_get_by_session_ordered_by_importance(lt):
    await lt.store("s1", "low", importance=0.1)
    await lt.store("s1", "high", importance=0.9)
    rows = await lt.get_by_session("s1")
    assert rows[0]["importance_score"] >= rows[-1]["importance_score"]


# ---------------------------------------------------------------------------
# update_importance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_importance_returns_true(lt):
    row_id = await lt.store("s1", "content", 0.5)
    updated = await lt.update_importance(row_id, 0.95)
    assert updated is True


@pytest.mark.asyncio
async def test_update_importance_persists(lt):
    row_id = await lt.store("s1", "content", 0.5)
    await lt.update_importance(row_id, 0.99)
    rows = await lt.get_by_session("s1")
    assert rows[0]["importance_score"] == pytest.approx(0.99)


@pytest.mark.asyncio
async def test_update_importance_missing_returns_false(lt):
    result = await lt.update_importance(99999, 0.5)
    assert result is False


# ---------------------------------------------------------------------------
# update_content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_content_returns_true(lt):
    row_id = await lt.store("s1", "original text", 0.5)
    updated = await lt.update_content(row_id, "edited text")
    assert updated is True


@pytest.mark.asyncio
async def test_update_content_persists(lt):
    row_id = await lt.store("s1", "original text", 0.5)
    await lt.update_content(row_id, "edited text")
    rows = await lt.get_by_session("s1")
    assert rows[0]["content"] == "edited text"


@pytest.mark.asyncio
async def test_update_content_leaves_importance_unchanged(lt):
    row_id = await lt.store("s1", "original text", 0.8)
    await lt.update_content(row_id, "edited text")
    rows = await lt.get_by_session("s1")
    assert rows[0]["importance_score"] == pytest.approx(0.8)


@pytest.mark.asyncio
async def test_update_content_missing_returns_false(lt):
    result = await lt.update_content(99999, "doesn't matter")
    assert result is False


# ---------------------------------------------------------------------------
# delete_entry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_entry_returns_true(lt):
    row_id = await lt.store("s1", "to delete", 0.5)
    deleted = await lt.delete_entry(row_id)
    assert deleted is True


@pytest.mark.asyncio
async def test_delete_entry_removes_from_db(lt):
    row_id = await lt.store("s1", "to delete", 0.5)
    await lt.delete_entry(row_id)
    rows = await lt.get_by_session("s1")
    assert not any(r["id"] == row_id for r in rows)


@pytest.mark.asyncio
async def test_delete_entry_missing_returns_false(lt):
    result = await lt.delete_entry(88888)
    assert result is False


# ---------------------------------------------------------------------------
# delete_old
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_old_zero_days_removes_nothing_recent(lt):
    await lt.store("s1", "recent content", 0.5)
    deleted = await lt.delete_old(days=365)
    assert deleted == 0


# ---------------------------------------------------------------------------
# prune_low_importance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_prune_low_importance_removes_below_threshold(lt):
    await lt.store("s1", "keep me", importance=0.8)
    await lt.store("s1", "prune me", importance=0.1)
    removed = await lt.prune_low_importance(threshold=0.3)
    assert removed == 1
    rows = await lt.get_by_session("s1")
    assert all(r["importance_score"] >= 0.3 for r in rows)


@pytest.mark.asyncio
async def test_prune_low_importance_nothing_to_remove(lt):
    await lt.store("s1", "high", importance=0.9)
    removed = await lt.prune_low_importance(threshold=0.05)
    assert removed == 0


# ---------------------------------------------------------------------------
# clear_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_all_removes_every_entry(lt):
    await lt.store("s1", "one", importance=0.9)
    await lt.store("s2", "two", importance=0.1)
    removed = await lt.clear_all()
    assert removed == 2
    assert await lt.get_by_session("s1") == []
    assert await lt.get_by_session("s2") == []


@pytest.mark.asyncio
async def test_clear_all_scoped_to_session(lt):
    await lt.store("s1", "keep me away", importance=0.9)
    await lt.store("s2", "untouched", importance=0.9)
    removed = await lt.clear_all(session_id="s1")
    assert removed == 1
    assert await lt.get_by_session("s1") == []
    assert len(await lt.get_by_session("s2")) == 1


@pytest.mark.asyncio
async def test_clear_all_empty_db_returns_zero(lt):
    removed = await lt.clear_all()
    assert removed == 0


# ---------------------------------------------------------------------------
# Auto-tagging (store) + search_by_tag
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_auto_extracts_tags_when_omitted(lt):
    await lt.store("s1", "Remember to read #python and #docker docs")
    rows = await lt.get_by_session("s1")
    tags = rows[0]["tags"].split(",")
    assert "python" in tags
    assert "docker" in tags


@pytest.mark.asyncio
async def test_store_explicit_tags_override_auto_extraction(lt):
    await lt.store("s1", "some content", tags=["custom-tag"])
    rows = await lt.get_by_session("s1")
    assert rows[0]["tags"] == "custom-tag"


@pytest.mark.asyncio
async def test_store_no_tags_extracted_gives_empty_string(lt):
    await lt.store("s1", "just a plain sentence")
    rows = await lt.get_by_session("s1")
    assert rows[0]["tags"] == ""


@pytest.mark.asyncio
async def test_search_by_tag_finds_matching_entries(lt):
    await lt.store("s1", "deploying with #docker today", importance=0.6)
    await lt.store("s1", "writing some javascript", importance=0.6)
    results = await lt.search_by_tag(session_id="s1", tag="docker")
    assert len(results) == 1
    assert "docker" in results[0]["tags"]


@pytest.mark.asyncio
async def test_search_by_tag_no_match_returns_empty(lt):
    await lt.store("s1", "#docker deployment", importance=0.5)
    results = await lt.search_by_tag(session_id="s1", tag="kubernetes")
    assert results == []


@pytest.mark.asyncio
async def test_search_by_tag_session_none_searches_all_sessions(lt):
    await lt.store("session-A", "#redis caching layer", importance=0.5)
    await lt.store("session-B", "#redis pub/sub setup", importance=0.5)
    results = await lt.search_by_tag(session_id=None, tag="redis")
    assert len(results) == 2


# ---------------------------------------------------------------------------
# list_stale_sessions
# ---------------------------------------------------------------------------


def _backdate_session(db_path: str, session_id: str, days_ago: int) -> None:
    import sqlite3

    conn = sqlite3.connect(db_path)
    conn.execute(
        f"UPDATE memory_entries SET last_accessed_at = datetime('now', '-{days_ago} days') "  # noqa: S608
        "WHERE session_id = ?",
        (session_id,),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_list_stale_sessions_finds_inactive(lt, tmp_path):
    await lt.store("fresh", "recent activity", importance=0.5)
    await lt.store("stale", "old activity", importance=0.5)
    _backdate_session(lt._db_path, "stale", days_ago=60)

    stale = await lt.list_stale_sessions(older_than_days=30)

    assert stale == ["stale"]


@pytest.mark.asyncio
async def test_list_stale_sessions_respects_threshold(lt):
    await lt.store("borderline", "some activity", importance=0.5)
    _backdate_session(lt._db_path, "borderline", days_ago=60)

    assert await lt.list_stale_sessions(older_than_days=90) == []


@pytest.mark.asyncio
async def test_list_stale_sessions_empty_db_returns_empty(lt):
    assert await lt.list_stale_sessions(older_than_days=30) == []


# ---------------------------------------------------------------------------
# Regression: delete_old / list_stale_sessions with ISO 8601 T-format dates
#
# LongTermMemory.store() writes last_accessed_at as ISO 8601 with a 'T'
# separator and UTC offset (e.g. 2024-01-15T10:30:00.000000+00:00).
# SQLite's datetime() computes YYYY-MM-DD HH:MM:SS (space, no offset).
# A plain string comparison `col < cutoff` fails because 'T' (ASCII 84)
# sorts higher than ' ' (ASCII 32), so every real-date row compares as
# "in the future" and nothing is ever deleted.  The fix wraps the column
# in datetime() so SQLite normalises both sides before comparing.
# ---------------------------------------------------------------------------


def _backdate_session_iso(db_path: str, session_id: str, days_ago: int) -> None:
    """Backdate entries using the ISO 8601 format that LongTermMemory.store() writes."""
    import sqlite3
    from datetime import datetime, timedelta, timezone

    ts = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    conn = sqlite3.connect(db_path)
    conn.execute(
        "UPDATE memory_entries SET last_accessed_at = ? WHERE session_id = ?",
        (ts, session_id),
    )
    conn.commit()
    conn.close()


@pytest.mark.asyncio
async def test_delete_old_removes_iso_backdated_entries(lt) -> None:
    """Regression: delete_old must fire when stored dates use ISO 8601 T-format."""
    await lt.store("s1", "old content", importance=0.5)
    _backdate_session_iso(lt._db_path, "s1", days_ago=60)

    deleted = await lt.delete_old(days=30)

    assert deleted == 1


@pytest.mark.asyncio
async def test_delete_old_spares_recent_iso_entries(lt) -> None:
    """Recent entries must NOT be deleted even when column has ISO 8601 T-format."""
    await lt.store("s1", "recent content", importance=0.5)
    # No backdating — entry is fresh from store()

    deleted = await lt.delete_old(days=30)

    assert deleted == 0


@pytest.mark.asyncio
async def test_list_stale_sessions_finds_iso_backdated_session(lt) -> None:
    """Regression: list_stale_sessions must match ISO 8601 T-format timestamps."""
    await lt.store("stale-iso", "old data", importance=0.5)
    _backdate_session_iso(lt._db_path, "stale-iso", days_ago=60)
    await lt.store("fresh-iso", "new data", importance=0.5)

    stale = await lt.list_stale_sessions(older_than_days=30)

    assert stale == ["stale-iso"]
    assert "fresh-iso" not in stale


# ---------------------------------------------------------------------------
# memory_entries_total gauge
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_init_schema_seeds_gauge_from_existing_rows(tmp_path):
    from cortexflow_ai.observability.metrics import REGISTRY

    db_path = str(tmp_path / "seed_gauge.db")
    lt_prep = LongTermMemory(db_path=db_path)
    await lt_prep.init_schema()
    await lt_prep.store("s1", "entry A")
    await lt_prep.store("s1", "entry B")

    # Re-open a fresh instance (simulates restart with pre-existing rows)
    gauge = REGISTRY.get("memory_entries_total")
    gauge.set(0.0)  # reset to 0 to detect seeding
    lt2 = LongTermMemory(db_path=db_path)
    await lt2.init_schema()

    snap = gauge.snapshot()
    assert snap.get("", 0.0) == 2.0, "init_schema must seed gauge from actual row count"


@pytest.mark.asyncio
async def test_store_increments_gauge(lt):
    from cortexflow_ai.observability.metrics import REGISTRY

    gauge = REGISTRY.get("memory_entries_total")
    before = gauge.snapshot().get("", 0.0)

    await lt.store("sess", "fact A")
    await lt.store("sess", "fact B")

    after = gauge.snapshot().get("", 0.0)
    assert after == before + 2.0, "store() must increment memory_entries_total by 1 per call"


@pytest.mark.asyncio
async def test_delete_entry_decrements_gauge(lt):
    from cortexflow_ai.observability.metrics import REGISTRY

    eid = await lt.store("sess", "deletable entry")
    gauge = REGISTRY.get("memory_entries_total")
    before = gauge.snapshot().get("", 0.0)

    deleted = await lt.delete_entry(eid)

    assert deleted is True
    after = gauge.snapshot().get("", 0.0)
    assert after == before - 1.0, "delete_entry() must decrement memory_entries_total on success"


@pytest.mark.asyncio
async def test_delete_entry_missing_does_not_touch_gauge(lt):
    from cortexflow_ai.observability.metrics import REGISTRY

    gauge = REGISTRY.get("memory_entries_total")
    before = gauge.snapshot().get("", 0.0)

    deleted = await lt.delete_entry(99999)

    assert deleted is False
    after = gauge.snapshot().get("", 0.0)
    assert after == before, "delete_entry() must not change gauge when row not found"
