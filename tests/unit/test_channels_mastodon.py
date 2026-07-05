"""Unit tests for cortexflow.channels.mastodon_ — MastodonAdapter."""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from cortexflow_ai.channels.mastodon_ import MastodonAdapter, _strip_html


def make_adapter(**overrides) -> MastodonAdapter:
    cfg = {
        "instance_url": "https://mastodon.social",
        "access_token": "token-abc",
        "bot_username": "@bot",
        **overrides,
    }
    return MastodonAdapter(cfg)


class _FakeStreamListener:
    """Stand-in for mastodon.StreamListener — a plain subclassable base."""


def _mock_mastodon_module() -> MagicMock:
    mod = MagicMock()
    mod.StreamListener = _FakeStreamListener
    mod.Mastodon = MagicMock()
    return mod


# ---------------------------------------------------------------------------
# _strip_html
# ---------------------------------------------------------------------------


def test_strip_html_removes_tags():
    assert _strip_html("<p>hello <b>world</b></p>") == "hello world"


def test_strip_html_empty_string():
    assert _strip_html("") == ""


# ---------------------------------------------------------------------------
# Construction / resolution
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "mastodon"


def test_defaults():
    adapter = MastodonAdapter({})
    assert adapter._instance_url == "https://mastodon.social"
    assert adapter._visibility == "unlisted"


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("MASTODON_TOKEN_TEST", "resolved-token")
    adapter = make_adapter(access_token="ENV:MASTODON_TOKEN_TEST")
    assert adapter._access_token == "resolved-token"


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert "instance_url" in schema["required"]
    assert "access_token" in schema["required"]


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_raises_if_mastodon_not_installed():
    adapter = make_adapter()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mastodon":
            raise ImportError("No module named 'mastodon'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        with pytest.raises(RuntimeError, match="Mastodon.py"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_success_starts_stream_task():
    adapter = make_adapter()
    mock_mastodon = _mock_mastodon_module()
    mock_client_instance = MagicMock()
    mock_client_instance.stream_user = MagicMock()  # returns immediately, doesn't block
    mock_mastodon.Mastodon.return_value = mock_client_instance

    with patch.dict("sys.modules", {"mastodon": mock_mastodon}):
        await adapter.connect()
        await asyncio.sleep(0.05)  # let the executor thread run _blocking_stream

    assert adapter._client is mock_client_instance
    assert adapter._stream_task is not None

    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_with_no_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_cancels_stream_task():
    adapter = make_adapter()
    adapter._client = MagicMock()

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._stream_task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._stream_task is None
    assert adapter._client is None


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_client_returns_none():
    adapter = make_adapter()
    result = await adapter.send("@alice@instance", "hi")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_status_id():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.status_post = MagicMock(return_value={"id": 9988})

    result = await adapter.send("@alice@instance", "hello")

    assert result == "9988"


@pytest.mark.asyncio
async def test_send_prepends_target_to_content():
    adapter = make_adapter()
    adapter._client = MagicMock()
    captured = {}

    def fake_post(content, **kwargs):
        captured["content"] = content
        return {"id": 1}

    adapter._client.status_post = fake_post

    await adapter.send("@alice@instance", "hello there")

    assert captured["content"] == "@alice@instance hello there"


@pytest.mark.asyncio
async def test_send_truncates_long_content():
    adapter = make_adapter()
    adapter._client = MagicMock()
    captured = {}

    def fake_post(content, **kwargs):
        captured["content"] = content
        return {"id": 1}

    adapter._client.status_post = fake_post

    await adapter.send("", "x" * 600)

    assert len(captured["content"]) == 500


@pytest.mark.asyncio
async def test_send_exception_returns_none():
    adapter = make_adapter()
    adapter._client = MagicMock()
    adapter._client.status_post = MagicMock(side_effect=Exception("API error"))

    result = await adapter.send("@alice@instance", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _blocking_stream — mastodon not installed
# ---------------------------------------------------------------------------


def test_blocking_stream_returns_if_mastodon_not_installed():
    adapter = make_adapter()
    adapter._client = MagicMock()
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mastodon":
            raise ImportError("No module named 'mastodon'")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        adapter._blocking_stream()  # should return quietly, not raise


def test_blocking_stream_no_client_does_not_call_stream_user():
    adapter = make_adapter()
    adapter._client = None
    mock_mastodon = _mock_mastodon_module()

    with patch.dict("sys.modules", {"mastodon": mock_mastodon}):
        adapter._blocking_stream()  # self._client is None -> stream_user never called


# ---------------------------------------------------------------------------
# _blocking_stream._Listener.on_notification — via stream_user callback
# ---------------------------------------------------------------------------


def _run_blocking_stream_with_notification(adapter: MastodonAdapter, notification: dict) -> None:
    adapter._client = MagicMock()
    adapter._client.stream_user = lambda listener: listener.on_notification(notification)
    mock_mastodon = _mock_mastodon_module()
    with patch.dict("sys.modules", {"mastodon": mock_mastodon}):
        adapter._blocking_stream()


def test_on_notification_ignores_non_mention():
    adapter = make_adapter()
    dispatched = []
    adapter.on_message(lambda msg: dispatched.append(msg))

    _run_blocking_stream_with_notification(adapter, {"type": "favourite"})

    assert dispatched == []


@pytest.mark.asyncio
async def test_on_notification_dispatches_mention():
    adapter = make_adapter()
    adapter._loop = asyncio.get_running_loop()  # set so run_coroutine_threadsafe has a target
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notification = {
        "type": "mention",
        "status": {
            "id": "555",
            "content": "<p>@bot hello there</p>",
            "account": {"acct": "alice@instance", "display_name": "Alice"},
            "media_attachments": [],
        },
    }
    _run_blocking_stream_with_notification(adapter, notification)
    # run_coroutine_threadsafe uses call_soon_threadsafe: first sleep turns the
    # threadsafe callback into a Task; second sleep lets the Task actually execute.
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "hello there"
    assert dispatched[0].sender_id == "alice@instance"
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].thread_id == "555"


def test_on_notification_empty_text_after_strip_not_dispatched():
    adapter = make_adapter()
    dispatched = []
    adapter.on_message(lambda msg: dispatched.append(msg))

    notification = {
        "type": "mention",
        "status": {
            "id": "1",
            "content": "<p>@bot</p>",
            "account": {"acct": "alice@instance"},
            "media_attachments": [],
        },
    }
    _run_blocking_stream_with_notification(adapter, notification)

    assert dispatched == []


@pytest.mark.asyncio
async def test_on_notification_builds_attachments_from_media():
    adapter = make_adapter()
    adapter._loop = asyncio.get_running_loop()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notification = {
        "type": "mention",
        "status": {
            "id": "2",
            "content": "<p>@bot check this out</p>",
            "account": {"acct": "alice@instance"},
            "media_attachments": [{"type": "image", "url": "https://example.com/pic.jpg"}],
        },
    }
    _run_blocking_stream_with_notification(adapter, notification)
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert len(dispatched[0].attachments) == 1
    assert dispatched[0].attachments[0].type == "image"
    assert dispatched[0].attachments[0].url == "https://example.com/pic.jpg"


# ---------------------------------------------------------------------------
# _stream_mentions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_mentions_swallows_cancelled_error(monkeypatch: pytest.MonkeyPatch):
    adapter = make_adapter()

    def raise_cancelled():
        raise asyncio.CancelledError()

    monkeypatch.setattr(adapter, "_blocking_stream", raise_cancelled)

    await adapter._stream_mentions()  # should not raise


@pytest.mark.asyncio
async def test_stream_mentions_swallows_generic_exception(monkeypatch: pytest.MonkeyPatch):
    adapter = make_adapter()

    def raise_generic():
        raise RuntimeError("stream broke")

    monkeypatch.setattr(adapter, "_blocking_stream", raise_generic)

    await adapter._stream_mentions()  # should swallow and log, not raise


def test_on_notification_no_handler_does_not_raise():
    adapter = make_adapter()
    notification = {
        "type": "mention",
        "status": {
            "id": "3",
            "content": "<p>@bot hi</p>",
            "account": {"acct": "alice@instance"},
            "media_attachments": [],
        },
    }
    _run_blocking_stream_with_notification(adapter, notification)  # no handler registered
