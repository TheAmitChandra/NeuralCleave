"""HTTP integration tests for neuralcleave.pwa.routes (pwa_router + push_router)."""

from __future__ import annotations

import pathlib
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.pwa import routes as pwa_routes_module
from neuralcleave.pwa.push import PushManager
from neuralcleave.pwa.routes import push_router, pwa_router

# ---------------------------------------------------------------------------
# Shared test app fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def app(tmp_path: pathlib.Path):
    """Minimal FastAPI app with both PWA routers and an isolated PushManager."""
    _app = FastAPI()
    _app.include_router(pwa_router)
    _app.include_router(push_router, prefix="/api/v1")

    # Isolate the module-level PushManager to a temp directory
    isolated_mgr = PushManager(store_path=tmp_path / "subs.json")
    with patch.object(pwa_routes_module, "_push_manager", isolated_mgr):
        yield _app


@pytest.fixture()
def client(app):
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ---------------------------------------------------------------------------
# GET /app — PWA shell
# ---------------------------------------------------------------------------


class TestPwaShell:
    def test_returns_200(self, client):
        resp = client.get("/app")
        assert resp.status_code == 200

    def test_content_type_html(self, client):
        resp = client.get("/app")
        assert "text/html" in resp.headers["content-type"]

    def test_contains_doctype(self, client):
        assert "<!doctype html>" in resp_text(client, "/app").lower()

    def test_contains_manifest_link(self, client):
        assert 'href="/manifest.json"' in resp_text(client, "/app")

    def test_contains_service_worker_registration(self, client):
        assert "serviceWorker" in resp_text(client, "/app")

    def test_contains_websocket_connect(self, client):
        assert "WebSocket" in resp_text(client, "/app")

    def test_contains_viewport_meta(self, client):
        assert 'name="viewport"' in resp_text(client, "/app")

    def test_contains_theme_color_meta(self, client):
        assert 'name="theme-color"' in resp_text(client, "/app")

    def test_contains_NeuralCleave_title(self, client):
        assert "NeuralCleave" in resp_text(client, "/app")

    def test_html_has_install_banner(self, client):
        assert "install-banner" in resp_text(client, "/app")

    def test_html_has_message_input(self, client):
        assert 'id="input"' in resp_text(client, "/app")

    def test_html_has_send_button(self, client):
        assert 'id="send"' in resp_text(client, "/app")


# ---------------------------------------------------------------------------
# GET /manifest.json
# ---------------------------------------------------------------------------


class TestManifest:
    def test_returns_200(self, client):
        resp = client.get("/manifest.json")
        assert resp.status_code == 200

    def test_content_type_manifest(self, client):
        resp = client.get("/manifest.json")
        assert "manifest" in resp.headers["content-type"] or "json" in resp.headers["content-type"]

    def test_json_parses(self, client):
        resp = client.get("/manifest.json")
        data = resp.json()
        assert isinstance(data, dict)

    def test_name_field(self, client):
        assert client.get("/manifest.json").json()["name"] == "NeuralCleave"

    def test_start_url_field(self, client):
        assert client.get("/manifest.json").json()["start_url"] == "/app"

    def test_display_standalone(self, client):
        assert client.get("/manifest.json").json()["display"] == "standalone"

    def test_icons_present(self, client):
        icons = client.get("/manifest.json").json()["icons"]
        assert len(icons) >= 2

    def test_has_192_icon(self, client):
        sizes = [i["sizes"] for i in client.get("/manifest.json").json()["icons"]]
        assert "192x192" in sizes

    def test_has_512_icon(self, client):
        sizes = [i["sizes"] for i in client.get("/manifest.json").json()["icons"]]
        assert "512x512" in sizes


# ---------------------------------------------------------------------------
# GET /sw.js — Service Worker
# ---------------------------------------------------------------------------


class TestServiceWorker:
    def test_returns_200(self, client):
        assert client.get("/sw.js").status_code == 200

    def test_content_type_javascript(self, client):
        resp = client.get("/sw.js")
        assert "javascript" in resp.headers["content-type"]

    def test_service_worker_allowed_header(self, client):
        resp = client.get("/sw.js")
        assert resp.headers.get("service-worker-allowed") == "/"

    def test_contains_install_event(self, client):
        assert "install" in client.get("/sw.js").text

    def test_contains_fetch_event(self, client):
        assert "fetch" in client.get("/sw.js").text

    def test_contains_push_event(self, client):
        assert "push" in client.get("/sw.js").text

    def test_contains_notificationclick(self, client):
        assert "notificationclick" in client.get("/sw.js").text

    def test_contains_cache_open(self, client):
        assert "caches.open" in client.get("/sw.js").text

    def test_contains_skip_waiting(self, client):
        assert "skipWaiting" in client.get("/sw.js").text


# ---------------------------------------------------------------------------
# GET /app-icon-*.svg — Icons
# ---------------------------------------------------------------------------


class TestIcons:
    def test_icon_192_returns_200(self, client):
        assert client.get("/app-icon-192.svg").status_code == 200

    def test_icon_512_returns_200(self, client):
        assert client.get("/app-icon-512.svg").status_code == 200

    def test_icon_192_content_type_svg(self, client):
        assert "svg" in client.get("/app-icon-192.svg").headers["content-type"]

    def test_icon_512_content_type_svg(self, client):
        assert "svg" in client.get("/app-icon-512.svg").headers["content-type"]

    def test_icon_192_has_svg_tag(self, client):
        assert "<svg" in client.get("/app-icon-192.svg").text

    def test_icon_512_has_svg_tag(self, client):
        assert "<svg" in client.get("/app-icon-512.svg").text


# ---------------------------------------------------------------------------
# GET /api/v1/push/vapid-public-key
# ---------------------------------------------------------------------------


class TestVapidPublicKey:
    def test_returns_503_when_not_configured(self, client):
        resp = client.get("/api/v1/push/vapid-public-key")
        assert resp.status_code == 503

    def test_returns_200_when_key_set(self, app, client):
        app.state.vapid_public_key = "BTEST_KEY"
        resp = client.get("/api/v1/push/vapid-public-key")
        assert resp.status_code == 200

    def test_returns_key_value(self, app, client):
        app.state.vapid_public_key = "BTEST_KEY"
        data = client.get("/api/v1/push/vapid-public-key").json()
        assert data["public_key"] == "BTEST_KEY"


# ---------------------------------------------------------------------------
# POST /api/v1/push/subscribe
# ---------------------------------------------------------------------------


class TestSubscribe:
    _VALID = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/aaa",
        "p256dh": "BN4qRX==",
        "auth": "secret",
    }

    def test_returns_201(self, client):
        resp = client.post("/api/v1/push/subscribe", json=self._VALID)
        assert resp.status_code == 201

    def test_returns_subscription_id(self, client):
        resp = client.post("/api/v1/push/subscribe", json=self._VALID)
        assert "subscription_id" in resp.json()

    def test_returns_status_subscribed(self, client):
        resp = client.post("/api/v1/push/subscribe", json=self._VALID)
        assert resp.json()["status"] == "subscribed"

    def test_invalid_json_returns_422(self, client):
        resp = client.post(
            "/api/v1/push/subscribe",
            content="NOT JSON",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    def test_missing_endpoint_returns_422(self, client):
        resp = client.post(
            "/api/v1/push/subscribe",
            json={"p256dh": "abc", "auth": "xyz"},
        )
        assert resp.status_code == 422

    def test_missing_p256dh_returns_422(self, client):
        resp = client.post(
            "/api/v1/push/subscribe",
            json={"endpoint": "https://a.com", "auth": "xyz"},
        )
        assert resp.status_code == 422

    def test_missing_auth_returns_422(self, client):
        resp = client.post(
            "/api/v1/push/subscribe",
            json={"endpoint": "https://a.com", "p256dh": "abc"},
        )
        assert resp.status_code == 422

    def test_optional_user_agent_accepted(self, client):
        body = {**self._VALID, "user_agent": "Chrome/120"}
        resp = client.post("/api/v1/push/subscribe", json=body)
        assert resp.status_code == 201

    def test_subscription_persisted_in_manager(self, client, app, tmp_path):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        mgr = pwa_routes_module._push_manager
        assert mgr.count() == 1

    def test_second_subscribe_same_endpoint_overwrites(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        client.post("/api/v1/push/subscribe", json=self._VALID)
        assert pwa_routes_module._push_manager.count() == 1


# ---------------------------------------------------------------------------
# DELETE /api/v1/push/subscribe/{id}
# ---------------------------------------------------------------------------


class TestUnsubscribe:
    _VALID = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/bbb",
        "p256dh": "BN4qRX==",
        "auth": "secret2",
    }

    def _subscribe(self, client):
        resp = client.post("/api/v1/push/subscribe", json=self._VALID)
        return resp.json()["subscription_id"]

    def test_returns_200_on_existing(self, client):
        sid = self._subscribe(client)
        resp = client.delete(f"/api/v1/push/subscribe/{sid}")
        assert resp.status_code == 200

    def test_returns_status_unsubscribed(self, client):
        sid = self._subscribe(client)
        resp = client.delete(f"/api/v1/push/subscribe/{sid}")
        assert resp.json()["status"] == "unsubscribed"

    def test_returns_404_for_nonexistent(self, client):
        resp = client.delete("/api/v1/push/subscribe/does_not_exist")
        assert resp.status_code == 404

    def test_subscription_removed_from_manager(self, client):
        sid = self._subscribe(client)
        client.delete(f"/api/v1/push/subscribe/{sid}")
        assert pwa_routes_module._push_manager.count() == 0


# ---------------------------------------------------------------------------
# GET /api/v1/push/subscriptions
# ---------------------------------------------------------------------------


class TestListSubscriptions:
    _VALID = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/ccc",
        "p256dh": "BN4q==",
        "auth": "sec3",
    }

    def test_returns_200(self, client):
        assert client.get("/api/v1/push/subscriptions").status_code == 200

    def test_empty_returns_count_zero(self, client):
        data = client.get("/api/v1/push/subscriptions").json()
        assert data["count"] == 0

    def test_empty_subscriptions_list(self, client):
        data = client.get("/api/v1/push/subscriptions").json()
        assert data["subscriptions"] == []

    def test_count_increases_after_subscribe(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        data = client.get("/api/v1/push/subscriptions").json()
        assert data["count"] == 1

    def test_subscription_entry_has_id(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        subs = client.get("/api/v1/push/subscriptions").json()["subscriptions"]
        assert "id" in subs[0]

    def test_subscription_entry_has_endpoint(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        subs = client.get("/api/v1/push/subscriptions").json()["subscriptions"]
        assert "endpoint" in subs[0]

    def test_long_endpoint_is_truncated(self, client):
        long_endpoint = "https://fcm.googleapis.com/fcm/send/" + "x" * 100
        client.post(
            "/api/v1/push/subscribe",
            json={"endpoint": long_endpoint, "p256dh": "abc", "auth": "xyz"},
        )
        subs = client.get("/api/v1/push/subscriptions").json()["subscriptions"]
        assert len(subs[0]["endpoint"]) <= 65


# ---------------------------------------------------------------------------
# POST /api/v1/push/notify
# ---------------------------------------------------------------------------


class TestNotify:
    _VALID = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/ddd",
        "p256dh": "BN4q==",
        "auth": "sec4",
    }

    def test_returns_200(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        resp = client.post(
            "/api/v1/push/notify", json={"title": "Hello", "body": "World"}
        )
        assert resp.status_code == 200

    def test_returns_sent_count(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        data = client.post(
            "/api/v1/push/notify", json={"title": "Hello", "body": "World"}
        ).json()
        assert data["sent"] == 1

    def test_no_subscribers_returns_zero(self, client):
        data = client.post(
            "/api/v1/push/notify", json={"title": "Hi", "body": "Nobody"}
        ).json()
        assert data["sent"] == 0

    def test_invalid_json_returns_422(self, client):
        resp = client.post(
            "/api/v1/push/notify",
            content="BADJSON",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 422

    def test_payload_size_in_response(self, client):
        client.post("/api/v1/push/subscribe", json=self._VALID)
        data = client.post(
            "/api/v1/push/notify", json={"title": "Hi", "body": "World"}
        ).json()
        assert "payload_size" in data

    def test_multiple_subscribers_counted(self, client):
        for i in range(3):
            client.post(
                "/api/v1/push/subscribe",
                json={
                    "endpoint": f"https://fcm.example.com/{i}",
                    "p256dh": "abc",
                    "auth": "xyz",
                },
            )
        data = client.post(
            "/api/v1/push/notify", json={"title": "Bulk", "body": "msg"}
        ).json()
        assert data["sent"] == 3


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def resp_text(client, path: str) -> str:
    return client.get(path).text
