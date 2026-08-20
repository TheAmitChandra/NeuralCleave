"""Tests for neuralcleave.plugins.state — persistent plugin enable/disable
state (P9, 2026-08-17 gap analysis).
"""

from __future__ import annotations

from neuralcleave.plugins.state import PluginStateStore


class TestDefaultEnabled:
    def test_unknown_plugin_defaults_to_enabled(self):
        store = PluginStateStore(db_path=None)
        assert store.is_enabled("never-touched") is True


class TestSetEnabled:
    def test_disable_then_check(self):
        store = PluginStateStore(db_path=None)
        store.set_enabled("my-plugin", False)
        assert store.is_enabled("my-plugin") is False

    def test_enable_after_disable(self):
        store = PluginStateStore(db_path=None)
        store.set_enabled("my-plugin", False)
        store.set_enabled("my-plugin", True)
        assert store.is_enabled("my-plugin") is True

    def test_list_disabled_only_includes_disabled(self):
        store = PluginStateStore(db_path=None)
        store.set_enabled("a", False)
        store.set_enabled("b", True)
        assert store.list_disabled() == ["a"]

    def test_list_disabled_empty_by_default(self):
        store = PluginStateStore(db_path=None)
        assert store.list_disabled() == []


class TestPersistence:
    def test_state_survives_reopening_same_db(self, tmp_path):
        db_path = str(tmp_path / "state.db")
        store1 = PluginStateStore(db_path=db_path)
        store1.set_enabled("my-plugin", False)
        store1.close()

        store2 = PluginStateStore(db_path=db_path)
        assert store2.is_enabled("my-plugin") is False

    def test_updating_an_existing_record_persists(self, tmp_path):
        db_path = str(tmp_path / "state.db")
        store1 = PluginStateStore(db_path=db_path)
        store1.set_enabled("my-plugin", False)
        store1.set_enabled("my-plugin", True)
        store1.close()

        store2 = PluginStateStore(db_path=db_path)
        assert store2.is_enabled("my-plugin") is True

    def test_no_db_path_keeps_state_in_memory_only(self):
        store1 = PluginStateStore(db_path=None)
        store1.set_enabled("my-plugin", False)

        store2 = PluginStateStore(db_path=None)
        assert store2.is_enabled("my-plugin") is True  # fresh instance, no shared state


class TestConnectionLifecycle:
    def test_close_clears_connection(self, tmp_path):
        store = PluginStateStore(db_path=str(tmp_path / "state.db"))
        assert store._db is not None
        store.close()
        assert store._db is None

    def test_close_on_in_memory_only_is_noop(self):
        store = PluginStateStore(db_path=None)
        store.close()  # must not raise
        assert store._db is None


class TestModuleSingleton:
    def test_state_store_singleton_has_persistence_enabled(self):
        from neuralcleave.plugins.state import STATE_STORE

        assert STATE_STORE._db is not None
