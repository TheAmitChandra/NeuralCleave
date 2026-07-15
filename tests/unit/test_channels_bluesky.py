"""Unit tests for cortexflow.channels.bluesky — BlueskyAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from cortexflow_ai.channels.bluesky import BlueskyAdapter, _utc_now

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides) -> BlueskyAdapter:
    cfg = {
        "handle": "bot.bsky.social",
        "password": "app-password-123",
        **overrides,
    }
    return BlueskyAdapter(cfg)


def _fake_session(post_data=None, get_data=None):
    """Return a minimal aiohttp.ClientSession-like mock."""
    post_data = post_data or {}
    get_data = get_data or {}

    class _Resp:
        def __init__(self, data):
            self._data = data
            self.status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return self._data

    class _Session:
        def post(self, *_, **__):
            return _Resp(post_data)

        def get(self, *_, **__):
            return _Resp(get_data)

        async def close(self):
            pass

    return _Session()


def _auth_response():
    return {"accessJwt": "acc-jwt", "refreshJwt": "ref-jwt", "did": "did:plc:bot123"}


# ---------------------------------------------------------------------------
# _utc_now
# ---------------------------------------------------------------------------


def test_utc_now_returns_z_suffix():
    ts = _utc_now()
    assert ts.endswith("Z")


def test_utc_now_format():
    ts = _utc_now()
    assert "T" in ts
    assert len(ts) == 24  # YYYY-MM-DDTHH:MM:SS.mmmZ


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "bluesky"


def test_defaults():
    a = BlueskyAdapter({})
    assert a._pds_url == "https://bsky.social"
    assert a._poll_interval == 30.0
    assert a._notify_types == ["mention"]
    assert a._handle == ""
    assert a._password == ""


def test_pds_url_trailing_slash_stripped():
    a = make_adapter(pds_url="https://bsky.social/")
    assert a._pds_url == "https://bsky.social"


def test_custom_poll_interval():
    a = make_adapter(poll_interval=60)
    assert a._poll_interval == 60.0


def test_custom_notify_types():
    a = make_adapter(notify_types=["mention", "reply"])
    assert a._notify_types == ["mention", "reply"]


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("BSKY_PASS_TEST", "secret-pw")
    a = make_adapter(password="ENV:BSKY_PASS_TEST")
    assert a._password == "secret-pw"


def test_resolve_env_missing_var(monkeypatch):
    monkeypatch.delenv("BSKY_MISSING_VAR", raising=False)
    a = make_adapter(password="ENV:BSKY_MISSING_VAR")
    assert a._password == ""


def test_resolve_plain_string_unchanged():
    a = make_adapter(password="plaintext")
    assert a._password == "plaintext"


# ---------------------------------------------------------------------------
# config schema
# ---------------------------------------------------------------------------


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "handle" in schema["required"]
    assert "password" in schema["required"]


def test_config_schema_has_optional_fields():
    schema = make_adapter().get_config_schema()
    props = schema["properties"]
    assert "pds_url" in props
    assert "poll_interval" in props
    assert "notify_types" in props


# ---------------------------------------------------------------------------
# connect() — import guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_aiohttp_not_installed():
    adapter = make_adapter()
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "aiohttp":
            raise ImportError("no aiohttp")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="aiohttp"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_raises_missing_handle():
    adapter = BlueskyAdapter({"password": "pw"})
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = _fake_session()
    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        with pytest.raises(RuntimeError, match="handle"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_raises_missing_password():
    adapter = BlueskyAdapter({"handle": "bot.bsky.social"})
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = _fake_session()
    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        with pytest.raises(RuntimeError, match="password"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_sets_jwt_and_did():
    adapter = make_adapter()
    session = _fake_session(post_data=_auth_response())
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = session

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        await adapter.connect()

    assert adapter._access_jwt == "acc-jwt"
    assert adapter._did == "did:plc:bot123"
    assert adapter._poll_task is not None

    await adapter.disconnect()


@pytest.mark.asyncio
async def test_connect_starts_poll_task():
    adapter = make_adapter()
    session = _fake_session(post_data=_auth_response())
    mock_aiohttp = MagicMock()
    mock_aiohttp.ClientSession.return_value = session

    with patch.dict("sys.modules", {"aiohttp": mock_aiohttp}):
        await adapter.connect()

    assert isinstance(adapter._poll_task, asyncio.Task)
    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_without_connect_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()
    assert adapter._poll_task is None
    assert adapter._session is None


@pytest.mark.asyncio
async def test_disconnect_cancels_poll_task():
    adapter = make_adapter()

    async def _run_forever():
        await asyncio.sleep(1000)

    adapter._poll_task = asyncio.create_task(_run_forever())
    adapter._session = _fake_session()
    await adapter.disconnect()

    assert adapter._poll_task is None


@pytest.mark.asyncio
async def test_disconnect_clears_jwt():
    adapter = make_adapter()
    adapter._access_jwt = "some-jwt"
    adapter._refresh_jwt = "some-refresh"
    adapter._session = _fake_session()
    await adapter.disconnect()
    assert adapter._access_jwt == ""
    assert adapter._refresh_jwt == ""


@pytest.mark.asyncio
async def test_disconnect_closes_session():
    adapter = make_adapter()
    closed = []
    session = _fake_session()

    async def _close():
        closed.append(True)

    session.close = _close  # type: ignore[method-assign]
    adapter._session = session

    await adapter.disconnect()
    assert closed


# ---------------------------------------------------------------------------
# is_connected (via base class property)
# ---------------------------------------------------------------------------


def test_is_connected_true_when_poll_task_present():
    adapter = make_adapter()
    adapter._poll_task = MagicMock()  # non-None sentinel — is_connected checks presence, not type
    assert adapter.is_connected is True


def test_is_connected_false_when_no_task():
    adapter = make_adapter()
    assert adapter.is_connected is False


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_session_returns_none():
    adapter = make_adapter()
    result = await adapter.send("user.bsky.social", "hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_no_jwt_returns_none():
    adapter = make_adapter()
    adapter._session = _fake_session()
    adapter._access_jwt = ""
    result = await adapter.send("user.bsky.social", "hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_prepends_at_mention():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"
    sent_bodies = []

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://uri/123"}

    class _Session:
        def post(self, url, json=None, headers=None, **kw):
            sent_bodies.append(json)
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter.send("alice.bsky.social", "hello")

    record = sent_bodies[0]["record"]
    assert record["text"].startswith("@alice.bsky.social")


@pytest.mark.asyncio
async def test_send_skips_prepend_when_mention_already_in_text():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"
    sent_bodies = []

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://uri/456"}

    class _Session:
        def post(self, url, json=None, headers=None, **kw):
            sent_bodies.append(json)
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter.send("@alice.bsky.social", "@alice.bsky.social already in text")

    record = sent_bodies[0]["record"]
    assert record["text"] == "@alice.bsky.social already in text"


@pytest.mark.asyncio
async def test_send_truncates_to_300_chars():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"
    captured = []

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://uri/789"}

    class _Session:
        def post(self, url, json=None, headers=None, **kw):
            captured.append(json)
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter.send("", "x" * 400)
    record = captured[0]["record"]
    assert len(record["text"]) == 300


@pytest.mark.asyncio
async def test_send_reply_to_sets_reply_field():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"
    captured = []

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://uri/555"}

    class _Session:
        def post(self, url, json=None, headers=None, **kw):
            captured.append(json)
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter.send("user", "text", reply_to="at://did:plc:x/post/123")

    record = captured[0]["record"]
    assert "reply" in record
    assert record["reply"]["parent"]["uri"] == "at://did:plc:x/post/123"


@pytest.mark.asyncio
async def test_send_non_at_uri_reply_to_ignored():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"
    captured = []

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://uri/001"}

    class _Session:
        def post(self, url, json=None, headers=None, **kw):
            captured.append(json)
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter.send("user", "text", reply_to="https://not-at-protocol")

    record = captured[0]["record"]
    assert "reply" not in record


@pytest.mark.asyncio
async def test_send_exception_returns_none():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"

    class _BadSession:
        def post(self, *_, **__):
            raise RuntimeError("network error")

        async def close(self):
            pass

    adapter._session = _BadSession()
    result = await adapter.send("user", "text")
    assert result is None


@pytest.mark.asyncio
async def test_send_returns_uri():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "acc"

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"uri": "at://did:plc:bot/app.bsky.feed.post/abc"}

    class _Session:
        def post(self, *_, **__):
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    result = await adapter.send("user", "hi")
    assert result == "at://did:plc:bot/app.bsky.feed.post/abc"


# ---------------------------------------------------------------------------
# ping()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ping_no_session_returns_false():
    adapter = make_adapter()
    assert await adapter.ping() is False


@pytest.mark.asyncio
async def test_ping_no_jwt_returns_false():
    adapter = make_adapter()
    adapter._session = _fake_session(get_data={"available": True})
    adapter._access_jwt = ""
    assert await adapter.ping() is False


@pytest.mark.asyncio
async def test_ping_success_returns_true():
    adapter = make_adapter()
    adapter._access_jwt = "jwt"
    adapter._session = _fake_session(get_data={"available": True})
    assert await adapter.ping() is True


@pytest.mark.asyncio
async def test_ping_exception_returns_false():
    adapter = make_adapter()
    adapter._access_jwt = "jwt"

    class _BadSession:
        def get(self, *_, **__):
            raise RuntimeError("timeout")

        async def close(self):
            pass

    adapter._session = _BadSession()
    assert await adapter.ping() is False


# ---------------------------------------------------------------------------
# _authenticate()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_stores_jwts():
    adapter = make_adapter()
    adapter._session = _fake_session(post_data=_auth_response())
    await adapter._authenticate()
    assert adapter._access_jwt == "acc-jwt"
    assert adapter._refresh_jwt == "ref-jwt"
    assert adapter._did == "did:plc:bot123"


# ---------------------------------------------------------------------------
# _refresh_token()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_token_falls_back_to_auth_when_no_refresh_jwt():
    adapter = make_adapter()
    adapter._session = _fake_session(post_data=_auth_response())
    adapter._refresh_jwt = ""
    await adapter._refresh_token()
    assert adapter._access_jwt == "acc-jwt"


@pytest.mark.asyncio
async def test_refresh_token_falls_back_to_auth_on_exception():
    adapter = make_adapter()
    adapter._refresh_jwt = "old-refresh"

    calls = []

    class _Resp:
        def __init__(self, ok):
            self.ok = ok
            self.status = 200 if ok else 401

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            if not self.ok:
                raise Exception("401")

        async def json(self):
            if not self.ok:
                raise Exception("401")
            return _auth_response()

    class _Session:
        def post(self, url, *_, **__):
            calls.append(url)
            if "refreshSession" in url:
                return _Resp(False)
            return _Resp(True)

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter._refresh_token()
    assert any("createSession" in c for c in calls)


# ---------------------------------------------------------------------------
# _build_inbound()
# ---------------------------------------------------------------------------


def test_build_inbound_returns_none_for_empty_text():
    adapter = make_adapter()
    notif = {"record": {"text": ""}, "uri": "at://x", "author": {}}
    assert adapter._build_inbound(notif, {}) is None


def test_build_inbound_fields():
    adapter = make_adapter()
    notif = {
        "record": {"text": "hello @bot"},
        "uri": "at://did:plc:alice/post/001",
        "indexedAt": "2026-07-15T12:00:00Z",
    }
    author = {"did": "did:plc:alice", "handle": "alice.bsky.social", "displayName": "Alice"}
    msg = adapter._build_inbound(notif, author)
    assert msg is not None
    assert msg.text == "hello @bot"
    assert msg.sender_id == "did:plc:alice"
    assert msg.sender_name == "Alice"
    assert msg.channel == "bluesky"
    assert msg.thread_id == "at://did:plc:alice/post/001"


def test_build_inbound_uses_handle_when_no_display_name():
    adapter = make_adapter()
    notif = {"record": {"text": "hi"}, "uri": "at://x"}
    author = {"did": "did:plc:alice", "handle": "alice.bsky.social"}
    msg = adapter._build_inbound(notif, author)
    assert msg.sender_name == "alice.bsky.social"


def test_build_inbound_attaches_images():
    adapter = make_adapter()
    notif = {
        "record": {
            "text": "look at this",
            "embed": {
                "$type": "app.bsky.embed.images",
                "images": [{"alt": "cat pic", "image": {}}],
            },
        },
        "uri": "at://x",
    }
    author = {"did": "did:plc:alice", "handle": "alice.bsky.social"}
    msg = adapter._build_inbound(notif, author)
    assert len(msg.attachments) == 1
    assert msg.attachments[0].type == "image"


def test_build_inbound_reply_to_id_from_record():
    adapter = make_adapter()
    notif = {
        "record": {
            "text": "reply text",
            "reply": {"parent": {"uri": "at://parent/uri"}},
        },
        "uri": "at://x",
    }
    author = {"did": "did:plc:alice", "handle": "alice.bsky.social"}
    msg = adapter._build_inbound(notif, author)
    assert msg.reply_to_id == "at://parent/uri"


# ---------------------------------------------------------------------------
# _poll_notifications() — echo guard and type filter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_skips_own_notifications():
    adapter = make_adapter()
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "jwt"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notifs = [
        {
            "reason": "mention",
            "isRead": False,
            "indexedAt": "2026-07-15T13:00:00Z",
            "author": {"did": "did:plc:bot", "handle": "bot.bsky.social"},
            "record": {"text": "self-mention"},
            "uri": "at://x",
        }
    ]

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"notifications": notifs, "seenAt": "2026-07-15T13:00:00Z"}

    class _Session:
        def get(self, *_, **__):
            return _Resp()

        def post(self, *_, **__):
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter._poll_notifications()
    assert dispatched == []


@pytest.mark.asyncio
async def test_poll_skips_wrong_notify_type():
    adapter = make_adapter(notify_types=["mention"])
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "jwt"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notifs = [
        {
            "reason": "like",
            "isRead": False,
            "indexedAt": "2026-07-15T13:00:00Z",
            "author": {"did": "did:plc:alice", "handle": "alice.bsky.social"},
            "record": {"text": "liked your post"},
            "uri": "at://x",
        }
    ]

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"notifications": notifs, "seenAt": "2026-07-15T13:00:00Z"}

    class _Session:
        def get(self, *_, **__):
            return _Resp()

        def post(self, *_, **__):
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter._poll_notifications()
    assert dispatched == []


@pytest.mark.asyncio
async def test_poll_dispatches_mention():
    adapter = make_adapter(notify_types=["mention"])
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "jwt"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notifs = [
        {
            "reason": "mention",
            "isRead": False,
            "indexedAt": "2026-07-15T14:00:00Z",
            "author": {"did": "did:plc:alice", "handle": "alice.bsky.social", "displayName": "Alice"},
            "record": {"text": "hey bot!"},
            "uri": "at://alice/post/99",
        }
    ]

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"notifications": notifs, "seenAt": "2026-07-15T14:00:00Z"}

    class _Session:
        def get(self, *_, **__):
            return _Resp()

        def post(self, *_, **__):
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter._poll_notifications()
    assert len(dispatched) == 1
    assert dispatched[0].text == "hey bot!"


@pytest.mark.asyncio
async def test_poll_skips_already_read_notifications():
    adapter = make_adapter(notify_types=["mention"])
    adapter._did = "did:plc:bot"
    adapter._access_jwt = "jwt"
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notifs = [
        {
            "reason": "mention",
            "isRead": True,
            "indexedAt": "2026-07-15T14:00:00Z",
            "author": {"did": "did:plc:alice", "handle": "alice.bsky.social"},
            "record": {"text": "already read mention"},
            "uri": "at://alice/post/100",
        }
    ]

    class _Resp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            pass

        def raise_for_status(self):
            pass

        async def json(self):
            return {"notifications": notifs, "seenAt": "2026-07-15T14:00:00Z"}

    class _Session:
        def get(self, *_, **__):
            return _Resp()

        def post(self, *_, **__):
            return _Resp()

        async def close(self):
            pass

    adapter._session = _Session()
    await adapter._poll_notifications()
    assert dispatched == []


# ---------------------------------------------------------------------------
# _poll_loop() — cancellation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_poll_loop_cancels_cleanly():
    adapter = make_adapter()
    adapter._access_jwt = "jwt"
    adapter._did = "did:plc:bot"

    poll_count = []

    async def fake_poll():
        poll_count.append(1)
        await asyncio.sleep(0)

    adapter._poll_notifications = fake_poll  # type: ignore[method-assign]
    adapter._poll_interval = 0.01

    task = asyncio.create_task(adapter._poll_loop())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert len(poll_count) >= 1


@pytest.mark.asyncio
async def test_poll_loop_continues_after_exception():
    adapter = make_adapter()
    adapter._poll_interval = 0.01

    call_count = [0]

    async def flaky_poll():
        call_count[0] += 1
        if call_count[0] < 3:
            raise RuntimeError("transient error")

    adapter._poll_notifications = flaky_poll  # type: ignore[method-assign]

    task = asyncio.create_task(adapter._poll_loop())
    await asyncio.sleep(0.1)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert call_count[0] >= 3


# ---------------------------------------------------------------------------
# _mark_seen()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_seen_swallows_exception():
    adapter = make_adapter()
    adapter._access_jwt = "jwt"

    class _BadSession:
        def post(self, *_, **__):
            raise RuntimeError("network error")

        async def close(self):
            pass

    adapter._session = _BadSession()
    await adapter._mark_seen("2026-07-15T00:00:00.000Z")  # should not raise
