"""Unit tests for cortexflow.memory.short_term — ShortTermMemory (Redis mocked)."""

from __future__ import annotations

import json
import types
from unittest.mock import AsyncMock, patch

import pytest

from cortexflow.memory.short_term import ShortTermMemory, _key, _pattern

# ---------------------------------------------------------------------------
# Key helpers
# ---------------------------------------------------------------------------


def test_key_format():
    assert _key("session-1", "last_topic") == "cf:stm:session-1:last_topic"


def test_pattern_format():
    assert _pattern("session-1") == "cf:stm:session-1:*"


# ---------------------------------------------------------------------------
# Mock factory
# ---------------------------------------------------------------------------


def _make_redis_client(store: dict | None = None):
    """Return an async mock redis client backed by an in-memory dict."""
    db = store if store is not None else {}
    r = AsyncMock()
    r.aclose = AsyncMock()

    async def _set(key, value, ex=None):
        db[key] = value

    async def _get(key):
        return db.get(key)

    async def _delete(*keys):
        return sum(1 for k in keys if db.pop(k, None) is not None)

    async def _keys(pattern):
        prefix = pattern.rstrip("*")
        return [k for k in db if k.startswith(prefix)]

    async def _ttl(key):
        return 3599 if key in db else -2

    r.set = AsyncMock(side_effect=_set)
    r.get = AsyncMock(side_effect=_get)
    r.delete = AsyncMock(side_effect=_delete)
    r.keys = AsyncMock(side_effect=_keys)
    r.ttl = AsyncMock(side_effect=_ttl)
    return r, db


def _patch_aioredis(r):
    """Return a context manager that replaces redis.asyncio so from_url returns r."""
    async def _from_url(*args, **kwargs):
        return r

    # Build fake module tree so `import redis.asyncio as aioredis` resolves correctly.
    fake_asyncio = types.ModuleType("redis.asyncio")
    fake_asyncio.from_url = _from_url  # type: ignore[attr-defined]

    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = fake_asyncio  # type: ignore[attr-defined]

    return patch.dict("sys.modules", {"redis": fake_redis, "redis.asyncio": fake_asyncio})


# ---------------------------------------------------------------------------
# store
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_store_returns_true_on_success():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.store("s1", "topic", "Python")
    assert result is True


@pytest.mark.asyncio
async def test_store_serialises_as_json():
    r, db = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        await stm.store("s1", "data", {"key": "value"})
    assert json.loads(db[_key("s1", "data")]) == {"key": "value"}


@pytest.mark.asyncio
async def test_store_returns_false_on_redis_error():
    r, _ = _make_redis_client()
    r.set = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.store("s1", "k", "v")
    assert result is False


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_returns_stored_value():
    r, _ = _make_redis_client({_key("s1", "lang"): json.dumps("Python")})
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        value = await stm.get("s1", "lang")
    assert value == "Python"


@pytest.mark.asyncio
async def test_get_returns_none_when_missing():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        value = await stm.get("s1", "no_such_key")
    assert value is None


@pytest.mark.asyncio
async def test_get_deserialises_dict():
    r, _ = _make_redis_client({_key("s1", "obj"): json.dumps({"a": 1})})
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        value = await stm.get("s1", "obj")
    assert value == {"a": 1}


@pytest.mark.asyncio
async def test_get_returns_none_on_redis_error():
    r, _ = _make_redis_client()
    r.get = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        value = await stm.get("s1", "k")
    assert value is None


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_returns_true_when_key_exists():
    r, db = _make_redis_client({_key("s1", "x"): json.dumps("val")})
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.delete("s1", "x")
    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.delete("s1", "ghost")
    assert result is False


@pytest.mark.asyncio
async def test_delete_removes_key_from_store():
    key = _key("s1", "todel")
    r, db = _make_redis_client({key: json.dumps("bye")})
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        await stm.delete("s1", "todel")
    assert key not in db


@pytest.mark.asyncio
async def test_delete_returns_false_on_redis_error():
    r, _ = _make_redis_client()
    r.delete = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.delete("s1", "k")
    assert result is False


# ---------------------------------------------------------------------------
# clear_session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_session_removes_all_session_keys():
    initial = {
        _key("s1", "a"): json.dumps("v1"),
        _key("s1", "b"): json.dumps("v2"),
        _key("s2", "c"): json.dumps("v3"),
    }
    r, db = _make_redis_client(initial)
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        removed = await stm.clear_session("s1")
    assert removed == 2
    assert _key("s2", "c") in db


@pytest.mark.asyncio
async def test_clear_session_empty_returns_zero():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.clear_session("no-session")
    assert result == 0


@pytest.mark.asyncio
async def test_clear_session_returns_zero_on_redis_error():
    r, _ = _make_redis_client()
    r.keys = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.clear_session("s1")
    assert result == 0


# ---------------------------------------------------------------------------
# get_all
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_all_returns_all_keys_for_session():
    initial = {
        _key("s1", "foo"): json.dumps("bar"),
        _key("s1", "num"): json.dumps(42),
        _key("s2", "other"): json.dumps("x"),
    }
    r, _ = _make_redis_client(initial)
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.get_all("s1")
    assert set(result.keys()) == {"foo", "num"}
    assert result["foo"] == "bar"
    assert result["num"] == 42


@pytest.mark.asyncio
async def test_get_all_empty_returns_empty_dict():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.get_all("s1")
    assert result == {}


@pytest.mark.asyncio
async def test_get_all_falls_back_to_raw_string_on_invalid_json():
    initial = {_key("s1", "raw"): "not valid json {{"}
    r, _ = _make_redis_client(initial)
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.get_all("s1")
    assert result["raw"] == "not valid json {{"


@pytest.mark.asyncio
async def test_get_all_returns_empty_dict_on_redis_error():
    r, _ = _make_redis_client()
    r.keys = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.get_all("s1")
    assert result == {}


# ---------------------------------------------------------------------------
# ttl
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ttl_returns_positive_for_existing_key():
    r, _ = _make_redis_client({_key("s1", "k"): json.dumps("v")})
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.ttl("s1", "k")
    assert result is not None
    assert result >= 0


@pytest.mark.asyncio
async def test_ttl_returns_none_for_missing_key():
    r, _ = _make_redis_client()
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.ttl("s1", "missing")
    assert result is None


@pytest.mark.asyncio
async def test_ttl_returns_none_on_redis_error():
    r, _ = _make_redis_client()
    r.ttl = AsyncMock(side_effect=ConnectionError("redis down"))
    with _patch_aioredis(r):
        stm = ShortTermMemory()
        result = await stm.ttl("s1", "k")
    assert result is None
