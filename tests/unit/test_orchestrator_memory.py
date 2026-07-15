"""Tests for cortexflow_ai.orchestrator.memory — MemoryEntry, MemoryNamespaceStore, MemoryNamespaceManager."""

from __future__ import annotations

import time

import pytest

from cortexflow_ai.orchestrator.memory import (
    MemoryEntry,
    MemoryNamespaceManager,
    MemoryNamespaceStore,
)

# ---------------------------------------------------------------------------
# MemoryEntry
# ---------------------------------------------------------------------------


class TestMemoryEntry:
    def test_required_fields_stored(self):
        e = MemoryEntry(key="k", value="v", namespace="ns")
        assert e.key == "k"
        assert e.value == "v"
        assert e.namespace == "ns"

    def test_created_at_auto_set(self):
        before = time.monotonic()
        e = MemoryEntry(key="k", value="v", namespace="ns")
        after = time.monotonic()
        assert before <= e.created_at <= after

    def test_tags_default_empty(self):
        e = MemoryEntry(key="k", value="v", namespace="ns")
        assert e.tags == []

    def test_tags_stored(self):
        e = MemoryEntry(key="k", value="v", namespace="ns", tags=["a", "b"])
        assert e.tags == ["a", "b"]

    def test_to_dict_keys(self):
        e = MemoryEntry(key="k", value="v", namespace="ns", tags=["t"])
        d = e.to_dict()
        assert set(d.keys()) == {"key", "value", "namespace", "created_at", "tags"}

    def test_to_dict_values(self):
        e = MemoryEntry(key="mykey", value=42, namespace="myns", tags=["x"])
        d = e.to_dict()
        assert d["key"] == "mykey"
        assert d["value"] == 42
        assert d["namespace"] == "myns"
        assert d["tags"] == ["x"]

    def test_value_can_be_dict(self):
        e = MemoryEntry(key="k", value={"a": 1}, namespace="ns")
        assert e.value == {"a": 1}

    def test_value_can_be_list(self):
        e = MemoryEntry(key="k", value=[1, 2, 3], namespace="ns")
        assert e.value == [1, 2, 3]

    def test_value_can_be_none(self):
        e = MemoryEntry(key="k", value=None, namespace="ns")
        assert e.value is None


# ---------------------------------------------------------------------------
# MemoryNamespaceStore — construction
# ---------------------------------------------------------------------------


class TestMemoryNamespaceStoreConstruction:
    def test_empty_namespace_raises(self):
        with pytest.raises(ValueError, match="namespace"):
            MemoryNamespaceStore("")

    def test_namespace_stored(self):
        s = MemoryNamespaceStore("work")
        assert s.namespace == "work"

    def test_max_entries_default(self):
        s = MemoryNamespaceStore("ns")
        assert s.max_entries == 1000

    def test_max_entries_custom(self):
        s = MemoryNamespaceStore("ns", max_entries=10)
        assert s.max_entries == 10

    def test_count_starts_at_zero(self):
        s = MemoryNamespaceStore("ns")
        assert s.count() == 0


# ---------------------------------------------------------------------------
# MemoryNamespaceStore — put / get / delete
# ---------------------------------------------------------------------------


class TestMemoryNamespaceStorePutGetDelete:
    @pytest.fixture
    def store(self):
        return MemoryNamespaceStore("test")

    def test_put_returns_entry(self, store):
        e = store.put("k1", "v1")
        assert isinstance(e, MemoryEntry)

    def test_put_stores_key_and_value(self, store):
        store.put("k1", "hello")
        assert store.get("k1").value == "hello"

    def test_put_sets_namespace(self, store):
        e = store.put("k1", "v")
        assert e.namespace == "test"

    def test_put_with_tags(self, store):
        store.put("k1", "v", tags=["important"])
        assert store.get("k1").tags == ["important"]

    def test_put_empty_key_raises(self, store):
        with pytest.raises(ValueError, match="key"):
            store.put("", "v")

    def test_put_overwrites_existing(self, store):
        store.put("k1", "old")
        store.put("k1", "new")
        assert store.get("k1").value == "new"

    def test_put_overwrite_does_not_grow_count(self, store):
        store.put("k1", "old")
        store.put("k1", "new")
        assert store.count() == 1

    def test_get_missing_returns_none(self, store):
        assert store.get("nonexistent") is None

    def test_delete_existing_returns_true(self, store):
        store.put("k1", "v")
        assert store.delete("k1") is True

    def test_delete_removes_entry(self, store):
        store.put("k1", "v")
        store.delete("k1")
        assert store.get("k1") is None

    def test_delete_nonexistent_returns_false(self, store):
        assert store.delete("nope") is False

    def test_count_tracks_additions(self, store):
        store.put("a", 1)
        store.put("b", 2)
        store.put("c", 3)
        assert store.count() == 3

    def test_count_tracks_deletions(self, store):
        store.put("a", 1)
        store.put("b", 2)
        store.delete("a")
        assert store.count() == 1


# ---------------------------------------------------------------------------
# MemoryNamespaceStore — LRU eviction
# ---------------------------------------------------------------------------


class TestMemoryNamespaceStoreEviction:
    def test_evicts_oldest_when_full(self):
        s = MemoryNamespaceStore("ns", max_entries=3)
        s.put("a", 1)
        s.put("b", 2)
        s.put("c", 3)
        s.put("d", 4)
        assert s.get("a") is None  # evicted

    def test_count_stays_at_max(self):
        s = MemoryNamespaceStore("ns", max_entries=3)
        for i in range(10):
            s.put(f"k{i}", i)
        assert s.count() == 3

    def test_eviction_preserves_newest(self):
        s = MemoryNamespaceStore("ns", max_entries=2)
        s.put("old", 0)
        s.put("mid", 1)
        s.put("new", 2)
        assert s.get("mid") is not None
        assert s.get("new") is not None

    def test_overwrite_moves_to_front(self):
        s = MemoryNamespaceStore("ns", max_entries=2)
        s.put("a", 1)
        s.put("b", 2)
        s.put("a", 99)  # refresh 'a'
        s.put("c", 3)   # should evict 'b', not 'a'
        assert s.get("a") is not None
        assert s.get("b") is None


# ---------------------------------------------------------------------------
# MemoryNamespaceStore — search and tag filtering
# ---------------------------------------------------------------------------


class TestMemoryNamespaceStoreSearch:
    @pytest.fixture
    def store(self):
        s = MemoryNamespaceStore("search_test")
        s.put("user:1", "Alice", tags=["user"])
        s.put("user:2", "Bob", tags=["user"])
        s.put("session:abc", "active", tags=["session"])
        s.put("note:1", "remember the milk", tags=["note", "important"])
        return s

    def test_search_by_key_substring(self, store):
        results = store.search("user:")
        assert len(results) == 2

    def test_search_by_value_substring(self, store):
        results = store.search("Alice")
        assert len(results) == 1
        assert results[0].key == "user:1"

    def test_search_case_insensitive(self, store):
        results = store.search("ALICE")
        assert len(results) == 1

    def test_search_no_match_returns_empty(self, store):
        results = store.search("zzz_not_there")
        assert results == []

    def test_search_with_tag_filter(self, store):
        results = store.search("", tag="user")
        assert len(results) == 2

    def test_search_tag_filter_miss(self, store):
        results = store.search("Alice", tag="session")
        assert results == []

    def test_list_by_tag(self, store):
        results = store.list_by_tag("important")
        assert len(results) == 1
        assert results[0].key == "note:1"

    def test_list_by_tag_nonexistent_empty(self, store):
        assert store.list_by_tag("unknown") == []


# ---------------------------------------------------------------------------
# MemoryNamespaceStore — clear and introspection
# ---------------------------------------------------------------------------


class TestMemoryNamespaceStoreClearAndIntrospection:
    @pytest.fixture
    def store(self):
        s = MemoryNamespaceStore("misc")
        s.put("a", 1)
        s.put("b", 2)
        return s

    def test_clear_returns_count(self, store):
        assert store.clear() == 2

    def test_clear_empties_store(self, store):
        store.clear()
        assert store.count() == 0

    def test_all_entries_order(self, store):
        keys = [e.key for e in store.all_entries()]
        assert keys == ["a", "b"]

    def test_all_keys(self, store):
        assert store.all_keys() == ["a", "b"]

    def test_stats_namespace(self, store):
        assert store.stats()["namespace"] == "misc"

    def test_stats_count(self, store):
        assert store.stats()["count"] == 2

    def test_stats_max_entries(self, store):
        assert store.stats()["max_entries"] == 1000

    def test_stats_utilization(self, store):
        assert 0 < store.stats()["utilization"] < 1


# ---------------------------------------------------------------------------
# MemoryNamespaceManager — construction and namespace access
# ---------------------------------------------------------------------------


class TestMemoryNamespaceManagerConstruction:
    def test_default_max_entries(self):
        m = MemoryNamespaceManager()
        assert m.default_max_entries == 1000

    def test_custom_max_entries(self):
        m = MemoryNamespaceManager(default_max_entries=50)
        assert m.default_max_entries == 50

    def test_namespace_count_zero(self):
        m = MemoryNamespaceManager()
        assert m.namespace_count() == 0

    def test_list_namespaces_empty(self):
        m = MemoryNamespaceManager()
        assert m.list_namespaces() == []


class TestMemoryNamespaceManagerNamespaceAccess:
    def test_namespace_creates_store(self):
        m = MemoryNamespaceManager()
        store = m.namespace("work")
        assert isinstance(store, MemoryNamespaceStore)

    def test_namespace_same_store_returned_on_second_call(self):
        m = MemoryNamespaceManager()
        s1 = m.namespace("work")
        s2 = m.namespace("work")
        assert s1 is s2

    def test_different_namespaces_different_stores(self):
        m = MemoryNamespaceManager()
        s1 = m.namespace("work")
        s2 = m.namespace("personal")
        assert s1 is not s2

    def test_namespace_count_increases(self):
        m = MemoryNamespaceManager()
        m.namespace("a")
        m.namespace("b")
        assert m.namespace_count() == 2

    def test_list_namespaces_names(self):
        m = MemoryNamespaceManager()
        m.namespace("alpha")
        m.namespace("beta")
        names = m.list_namespaces()
        assert "alpha" in names
        assert "beta" in names

    def test_empty_namespace_name_raises(self):
        m = MemoryNamespaceManager()
        with pytest.raises(ValueError, match="ns"):
            m.namespace("")


# ---------------------------------------------------------------------------
# MemoryNamespaceManager — convenience CRUD
# ---------------------------------------------------------------------------


class TestMemoryNamespaceManagerCRUD:
    @pytest.fixture
    def mgr(self):
        return MemoryNamespaceManager()

    def test_put_and_get(self, mgr):
        mgr.put("ns1", "k1", "hello")
        e = mgr.get("ns1", "k1")
        assert e is not None
        assert e.value == "hello"

    def test_get_missing_returns_none(self, mgr):
        assert mgr.get("ns1", "missing") is None

    def test_delete_returns_true(self, mgr):
        mgr.put("ns1", "k", "v")
        assert mgr.delete("ns1", "k") is True

    def test_delete_removes(self, mgr):
        mgr.put("ns1", "k", "v")
        mgr.delete("ns1", "k")
        assert mgr.get("ns1", "k") is None

    def test_delete_nonexistent_false(self, mgr):
        assert mgr.delete("ns1", "no") is False

    def test_search_cross_namespace(self, mgr):
        mgr.put("ns1", "key", "apple")
        mgr.put("ns2", "key", "banana")
        r1 = mgr.search("ns1", "apple")
        r2 = mgr.search("ns2", "apple")
        assert len(r1) == 1
        assert len(r2) == 0

    def test_isolation_between_namespaces(self, mgr):
        mgr.put("work", "secret", "project X")
        assert mgr.get("personal", "secret") is None


# ---------------------------------------------------------------------------
# MemoryNamespaceManager — clear and drop namespace
# ---------------------------------------------------------------------------


class TestMemoryNamespaceManagerLifecycle:
    @pytest.fixture
    def mgr(self):
        m = MemoryNamespaceManager()
        m.put("a", "k1", "v1")
        m.put("a", "k2", "v2")
        m.put("b", "k3", "v3")
        return m

    def test_clear_namespace_returns_count(self, mgr):
        assert mgr.clear_namespace("a") == 2

    def test_clear_namespace_empties_it(self, mgr):
        mgr.clear_namespace("a")
        assert mgr.get("a", "k1") is None

    def test_clear_nonexistent_namespace_returns_zero(self, mgr):
        assert mgr.clear_namespace("does_not_exist") == 0

    def test_clear_does_not_affect_other_namespace(self, mgr):
        mgr.clear_namespace("a")
        assert mgr.get("b", "k3") is not None

    def test_drop_namespace_returns_true(self, mgr):
        assert mgr.drop_namespace("a") is True

    def test_drop_namespace_removes_store(self, mgr):
        mgr.drop_namespace("a")
        assert "a" not in mgr.list_namespaces()

    def test_drop_nonexistent_returns_false(self, mgr):
        assert mgr.drop_namespace("z") is False


# ---------------------------------------------------------------------------
# MemoryNamespaceManager — global stats
# ---------------------------------------------------------------------------


class TestMemoryNamespaceManagerStats:
    def test_global_stats_empty(self):
        m = MemoryNamespaceManager()
        s = m.global_stats()
        assert s["namespace_count"] == 0
        assert s["total_entries"] == 0

    def test_global_stats_counts_all(self):
        m = MemoryNamespaceManager()
        m.put("a", "k1", "v")
        m.put("a", "k2", "v")
        m.put("b", "k3", "v")
        s = m.global_stats()
        assert s["namespace_count"] == 2
        assert s["total_entries"] == 3

    def test_global_stats_namespaces_list(self):
        m = MemoryNamespaceManager()
        m.put("x", "k", "v")
        s = m.global_stats()
        assert len(s["namespaces"]) == 1

    def test_namespace_stats_exists(self):
        m = MemoryNamespaceManager()
        m.put("work", "k", "v")
        s = m.namespace_stats("work")
        assert s is not None
        assert s["namespace"] == "work"
        assert s["count"] == 1

    def test_namespace_stats_nonexistent_returns_none(self):
        m = MemoryNamespaceManager()
        assert m.namespace_stats("nope") is None
