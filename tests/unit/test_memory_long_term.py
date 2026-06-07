"""Unit tests for cortexflow.memory.long_term — LongTermMemory SQLite CRUD."""

from __future__ import annotations

import pytest

from cortexflow.memory.long_term import LongTermMemory


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
    row_id = await lt.store("s1", "no importance given")
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
async def test_search_ordered_by_importance(lt):
    await lt.store("s1", "match low", importance=0.2)
    await lt.store("s1", "match high", importance=0.9)
    results = await lt.search(session_id="s1", query="match")
    assert results[0]["importance_score"] >= results[-1]["importance_score"]


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
