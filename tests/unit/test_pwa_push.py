"""Tests for cortexflow_ai.pwa.push — PushSubscription, PushManager, generate_vapid_keys."""

from __future__ import annotations

import json
import pathlib
from unittest.mock import patch

import pytest

from cortexflow_ai.pwa.push import PushManager, PushSubscription, generate_vapid_keys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_sub(**kwargs) -> PushSubscription:
    defaults = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/AAABBB",
        "p256dh": "BN4qRXE_2xp==",
        "auth": "secret_auth",
    }
    defaults.update(kwargs)
    return PushSubscription(**defaults)


def _make_manager(tmp_path: pathlib.Path) -> PushManager:
    return PushManager(store_path=tmp_path / "push_subscriptions.json")


# ---------------------------------------------------------------------------
# PushSubscription dataclass
# ---------------------------------------------------------------------------


class TestPushSubscription:
    def test_required_fields_stored(self):
        sub = _make_sub()
        assert sub.endpoint == "https://fcm.googleapis.com/fcm/send/AAABBB"
        assert sub.p256dh == "BN4qRXE_2xp=="
        assert sub.auth == "secret_auth"

    def test_optional_user_agent_default_empty(self):
        sub = _make_sub()
        assert sub.user_agent == ""

    def test_optional_created_at_default_empty(self):
        sub = _make_sub()
        assert sub.created_at == ""

    def test_optional_fields_set(self):
        sub = _make_sub(user_agent="Chrome/120", created_at="2026-07-15T00:00:00Z")
        assert sub.user_agent == "Chrome/120"
        assert sub.created_at == "2026-07-15T00:00:00Z"

    def test_to_dict_returns_dict(self):
        sub = _make_sub()
        d = sub.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_contains_all_fields(self):
        sub = _make_sub(user_agent="Safari", created_at="2026-07-15T00:00:00Z")
        d = sub.to_dict()
        assert set(d.keys()) == {"endpoint", "p256dh", "auth", "user_agent", "created_at"}

    def test_from_dict_roundtrip(self):
        sub = _make_sub(user_agent="Firefox", created_at="2026-07-15T10:00:00Z")
        restored = PushSubscription.from_dict(sub.to_dict())
        assert restored.endpoint == sub.endpoint
        assert restored.p256dh == sub.p256dh
        assert restored.auth == sub.auth
        assert restored.user_agent == sub.user_agent
        assert restored.created_at == sub.created_at

    def test_from_dict_optional_defaults(self):
        d = {"endpoint": "https://example.com", "p256dh": "abc", "auth": "xyz"}
        sub = PushSubscription.from_dict(d)
        assert sub.user_agent == ""
        assert sub.created_at == ""

    def test_subscription_id_is_16_chars(self):
        sub = _make_sub()
        assert len(sub.subscription_id) == 16

    def test_subscription_id_is_hex(self):
        sub = _make_sub()
        int(sub.subscription_id, 16)  # must not raise

    def test_subscription_id_stable_same_endpoint(self):
        s1 = _make_sub(endpoint="https://fcm.example.com/abc")
        s2 = _make_sub(endpoint="https://fcm.example.com/abc")
        assert s1.subscription_id == s2.subscription_id

    def test_subscription_id_differs_for_different_endpoints(self):
        s1 = _make_sub(endpoint="https://fcm.example.com/aaa")
        s2 = _make_sub(endpoint="https://fcm.example.com/bbb")
        assert s1.subscription_id != s2.subscription_id

    def test_to_dict_is_json_serializable(self):
        sub = _make_sub()
        assert json.dumps(sub.to_dict())


# ---------------------------------------------------------------------------
# PushManager — loading and persistence
# ---------------------------------------------------------------------------


class TestPushManagerPersistence:
    def test_count_zero_on_empty_store(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.count() == 0

    def test_add_returns_subscription_id(self, tmp_path):
        mgr = _make_manager(tmp_path)
        sid = mgr.add(_make_sub())
        assert isinstance(sid, str) and len(sid) == 16

    def test_add_persists_to_file(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub())
        assert mgr.store_path.exists()

    def test_persisted_file_is_valid_json(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub())
        content = json.loads(mgr.store_path.read_text())
        assert isinstance(content, dict)

    def test_add_then_count(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub())
        assert mgr.count() == 1

    def test_add_two_different_endpoints_count_two(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub(endpoint="https://fcm.example.com/aaa"))
        mgr.add(_make_sub(endpoint="https://fcm.example.com/bbb"))
        assert mgr.count() == 2

    def test_add_same_endpoint_overwrites(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub(user_agent="v1"))
        mgr.add(_make_sub(user_agent="v2"))
        assert mgr.count() == 1
        subs = mgr.list_all()
        assert subs[0].user_agent == "v2"

    def test_reload_from_file(self, tmp_path):
        mgr1 = _make_manager(tmp_path)
        mgr1.add(_make_sub())
        # New manager instance reads from same file
        mgr2 = PushManager(store_path=tmp_path / "push_subscriptions.json")
        assert mgr2.count() == 1

    def test_reload_preserves_all_fields(self, tmp_path):
        mgr1 = _make_manager(tmp_path)
        original = _make_sub(user_agent="Chrome", created_at="2026-07-15T00:00:00Z")
        mgr1.add(original)
        mgr2 = PushManager(store_path=tmp_path / "push_subscriptions.json")
        subs = mgr2.list_all()
        assert subs[0].user_agent == "Chrome"
        assert subs[0].created_at == "2026-07-15T00:00:00Z"

    def test_corrupt_file_starts_fresh(self, tmp_path):
        store = tmp_path / "push_subscriptions.json"
        store.write_text("NOT JSON", encoding="utf-8")
        mgr = PushManager(store_path=store)
        assert mgr.count() == 0

    def test_store_dir_created_if_missing(self, tmp_path):
        nested = tmp_path / "deep" / "nested"
        mgr = PushManager(store_path=nested / "push_subscriptions.json")
        mgr.add(_make_sub())
        assert (nested / "push_subscriptions.json").exists()


# ---------------------------------------------------------------------------
# PushManager — CRUD
# ---------------------------------------------------------------------------


class TestPushManagerCRUD:
    def test_get_existing(self, tmp_path):
        mgr = _make_manager(tmp_path)
        sub = _make_sub()
        mgr.add(sub)
        fetched = mgr.get(sub.subscription_id)
        assert fetched is not None
        assert fetched.endpoint == sub.endpoint

    def test_get_missing_returns_none(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.get("nonexistent_id") is None

    def test_remove_existing_returns_true(self, tmp_path):
        mgr = _make_manager(tmp_path)
        sub = _make_sub()
        mgr.add(sub)
        assert mgr.remove(sub.subscription_id) is True

    def test_remove_reduces_count(self, tmp_path):
        mgr = _make_manager(tmp_path)
        sub = _make_sub()
        mgr.add(sub)
        mgr.remove(sub.subscription_id)
        assert mgr.count() == 0

    def test_remove_nonexistent_returns_false(self, tmp_path):
        mgr = _make_manager(tmp_path)
        assert mgr.remove("no_such_id") is False

    def test_remove_persists_deletion(self, tmp_path):
        mgr = _make_manager(tmp_path)
        sub = _make_sub()
        mgr.add(sub)
        mgr.remove(sub.subscription_id)
        mgr2 = PushManager(store_path=tmp_path / "push_subscriptions.json")
        assert mgr2.count() == 0

    def test_list_all_returns_list(self, tmp_path):
        mgr = _make_manager(tmp_path)
        result = mgr.list_all()
        assert isinstance(result, list)

    def test_list_all_returns_all_subscriptions(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub(endpoint="https://a.example.com"))
        mgr.add(_make_sub(endpoint="https://b.example.com"))
        mgr.add(_make_sub(endpoint="https://c.example.com"))
        assert len(mgr.list_all()) == 3

    def test_clear_removes_all(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub(endpoint="https://a.example.com"))
        mgr.add(_make_sub(endpoint="https://b.example.com"))
        mgr.clear()
        assert mgr.count() == 0

    def test_clear_writes_empty_json(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub())
        mgr.clear()
        content = json.loads(mgr.store_path.read_text())
        assert content == {}

    def test_clear_when_file_absent_does_not_error(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.clear()  # file does not exist yet; should not raise

    def test_list_all_returns_push_subscription_objects(self, tmp_path):
        mgr = _make_manager(tmp_path)
        mgr.add(_make_sub())
        for s in mgr.list_all():
            assert isinstance(s, PushSubscription)


# ---------------------------------------------------------------------------
# generate_vapid_keys
# ---------------------------------------------------------------------------


class TestGenerateVapidKeys:
    def test_returns_dict(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert isinstance(result, dict)

    def test_has_public_key(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert "public_key" in result

    def test_has_private_key(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert "private_key" in result

    def test_public_key_is_string(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert isinstance(result["public_key"], str)

    def test_private_key_is_string(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert isinstance(result["private_key"], str)

    def test_public_key_url_safe_base64(self):
        pytest.importorskip("cryptography")
        import base64

        result = generate_vapid_keys()
        # Should decode without error
        padded = result["public_key"] + "=" * (4 - len(result["public_key"]) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        assert len(decoded) > 0

    def test_private_key_url_safe_base64(self):
        pytest.importorskip("cryptography")
        import base64

        result = generate_vapid_keys()
        padded = result["private_key"] + "=" * (4 - len(result["private_key"]) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        assert len(decoded) > 0

    def test_public_key_no_padding(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert "=" not in result["public_key"]

    def test_private_key_no_padding(self):
        pytest.importorskip("cryptography")
        result = generate_vapid_keys()
        assert "=" not in result["private_key"]

    def test_public_key_65_bytes_uncompressed(self):
        pytest.importorskip("cryptography")
        import base64

        result = generate_vapid_keys()
        padded = result["public_key"] + "=" * (4 - len(result["public_key"]) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        # Uncompressed EC point = 04 || 32 bytes X || 32 bytes Y = 65 bytes
        assert len(decoded) == 65
        assert decoded[0] == 0x04

    def test_private_key_32_bytes(self):
        pytest.importorskip("cryptography")
        import base64

        result = generate_vapid_keys()
        padded = result["private_key"] + "=" * (4 - len(result["private_key"]) % 4)
        decoded = base64.urlsafe_b64decode(padded)
        assert len(decoded) == 32

    def test_two_calls_produce_different_keys(self):
        pytest.importorskip("cryptography")
        k1 = generate_vapid_keys()
        k2 = generate_vapid_keys()
        assert k1["public_key"] != k2["public_key"]
        assert k1["private_key"] != k2["private_key"]

    def test_missing_cryptography_raises_import_error(self):
        import sys

        # Blank out all cryptography sub-modules to force ImportError on lazy import
        crypto_keys = {k: None for k in sys.modules if "cryptography" in k}
        with patch.dict("sys.modules", crypto_keys):
            with pytest.raises(ImportError, match="cryptography"):
                generate_vapid_keys()

    def test_import_error_message_contains_install_hint(self):
        import sys

        crypto_keys = {k: None for k in sys.modules if "cryptography" in k}
        with patch.dict("sys.modules", crypto_keys):
            with pytest.raises(ImportError, match="pip install cryptography"):
                generate_vapid_keys()
