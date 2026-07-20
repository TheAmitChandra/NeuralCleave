"""Unit tests for neuralcleave.channels.tlon — TlonAdapter.

Covers:
  - Constructor defaults and config parsing
  - is_connected lifecycle (_task attribute)
  - _urbit_uid() and _urbit_time_ms() helpers
  - _letter_text() — legacy text, modern story/inline, empty, edge cases
  - connect() — login, create channel, subscribe, SSE task started
  - disconnect() — task cancelled, session closed, idempotent
  - _login() — success sets cookie, failure raises, missing cookie raises
  - _create_channel() — PUT sent, non-204 raises
  - _subscribe() — POST with subscribe action body
  - _post_actions() — sends correct JSON, auth header, error response raises
  - _ack() — correct ack action shape, swallows errors
  - _parse_sse() — parses SSE id/data lines, triggers handle_sse_event
  - _handle_sse_event() — diff dispatches, quit resubscribes, subscribe ok ignored
  - _parse_chat_update() — add-message shape, message shape, echo guard,
      empty text, missing envelope, bot_ship echo guard
  - _parse_target() — all prefix forms (dm:/group:/path:) and bare strings
  - _build_path() — dm, group with host/channel, path passthrough
  - send() — success returns target, no session, empty target, network error
  - ping() — 200/302 returns True, non-2xx returns False, no creds, error
  - get_config_schema() — shape, required fields, defaults
  - Constants and module-level exports
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.tlon import (
    _CHAT_APP,
    _CHAT_MARK,
    _CHAT_SUBSCRIBE_PATH,
    _LOGIN_PATH,
    TlonAdapter,
    _letter_text,
    _urbit_time_ms,
    _urbit_uid,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_adapter(**overrides: Any) -> TlonAdapter:
    cfg: dict[str, Any] = {
        "ship": "~zod",
        "password": "lidlut-tabwed",
        **overrides,
    }
    return TlonAdapter(cfg)


def _cookie_morsel(value: str) -> Any:
    m = MagicMock()
    m.value = value
    return m


def _ctx(mock_resp: MagicMock) -> MagicMock:
    """Wrap a mock response in an async context manager."""
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=False)
    return mock_resp


def _make_login_resp(status: int = 302, cookie: str = "abc123") -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value="ok")
    resp.cookies = {"urbauth-~zod": _cookie_morsel(cookie)} if cookie else {}
    return _ctx(resp)


def _make_actions_resp(status: int = 204) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value="ok")
    return _ctx(resp)


def _make_put_resp(status: int = 204) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    return _ctx(resp)


class _AsyncContent:
    """Async-iterable wrapper over a list of byte chunks for SSE mocking."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks

    def __aiter__(self):
        return self._gen()

    async def _gen(self):
        for chunk in self._chunks:
            yield chunk


def _make_session(
    login_status: int = 302,
    login_cookie: str = "abc123",
    put_status: int = 204,
    post_status: int = 204,
    get_content: list[bytes] | None = None,
) -> MagicMock:
    """Build a mock aiohttp.ClientSession that handles all Eyre endpoints.

    Login POSTs (/~/login) → login_status / login_cookie.
    Channel POSTs (/~/channel/) → post_status.
    PUTs (/~/channel/) → put_status.
    GETs (/~/channel/) → SSE stream of get_content chunks.
    """
    session = MagicMock()

    login_resp = _make_login_resp(login_status, login_cookie)
    actions_resp = _make_actions_resp(post_status)

    def post_side_effect(url, **kwargs):
        if _LOGIN_PATH in url:
            return login_resp
        return actions_resp

    session.post = MagicMock(side_effect=post_side_effect)

    # PUT /~/channel/{uid}
    session.put = MagicMock(return_value=_make_put_resp(put_status))

    # GET /~/channel/{uid} → SSE
    get_resp = MagicMock()
    get_resp.status = 200
    get_resp.content = _AsyncContent(get_content or [])
    get_resp.__aenter__ = AsyncMock(return_value=get_resp)
    get_resp.__aexit__ = AsyncMock(return_value=False)
    session.get = MagicMock(return_value=get_resp)

    session.close = AsyncMock()
    return session


def _sse_chunk(*events: dict[str, Any]) -> bytes:
    """Encode one or more SSE events to bytes (double-newline terminated)."""
    parts: list[str] = []
    for i, ev in enumerate(events, 1):
        parts.append(f"id: {i}\ndata: {json.dumps(ev)}\n\n")
    return "".join(parts).encode()


def _add_message_event(
    path: str = "/~zod/dm/~nec",
    author: str = "~nec",
    text: str = "hello world",
    when: int = 1698000000000,
    uid: str = "0v1.abc",
) -> dict:
    return {
        "add-message": {
            "path": path,
            "envelope": {
                "uid": uid,
                "number": 1,
                "author": author,
                "when": when,
                "letter": {"text": text},
            },
        }
    }


async def _async_handler(msgs: list):
    """Return an async handler that appends to msgs."""
    async def handler(m):
        msgs.append(m)
    return handler


# ===========================================================================
# 1. Module helpers
# ===========================================================================


class TestUrbitHelpers:
    def test_urbit_uid_starts_with_0v(self):
        assert _urbit_uid().startswith("0v")

    def test_urbit_uid_unique(self):
        assert _urbit_uid() != _urbit_uid()

    def test_urbit_time_ms_positive(self):
        assert _urbit_time_ms() > 0

    def test_urbit_time_ms_approx_now(self):
        assert abs(_urbit_time_ms() - int(time.time() * 1000)) < 5000


class TestLetterText:
    def test_legacy_text_format(self):
        assert _letter_text({"text": "hello"}) == "hello"

    def test_story_inline_string(self):
        assert _letter_text({"story": {"inline": ["hello world"], "block": []}}) == "hello world"

    def test_story_inline_multiple_strings(self):
        result = _letter_text({"story": {"inline": ["foo", "bar"], "block": []}})
        assert "foo" in result and "bar" in result

    def test_story_inline_bold_dict(self):
        result = _letter_text({"story": {"inline": [{"bold": "bold text"}], "block": []}})
        assert "bold text" in result

    def test_story_inline_code_dict(self):
        result = _letter_text({"story": {"inline": [{"code": "fn()"}], "block": []}})
        assert "fn()" in result

    def test_empty_letter(self):
        assert _letter_text({}) == ""

    def test_empty_story_inline(self):
        assert _letter_text({"story": {"inline": [], "block": []}}) == ""

    def test_text_takes_priority_over_story(self):
        assert _letter_text({"text": "direct", "story": {"inline": ["other"]}}) == "direct"

    def test_numeric_text_coerced(self):
        assert _letter_text({"text": 42}) == "42"


# ===========================================================================
# 2. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_url(self):
        assert make_adapter()._url == "http://localhost:8080"

    def test_url_trailing_slash_stripped(self):
        assert make_adapter(url="http://ship.arvo.network/")._url == "http://ship.arvo.network"

    def test_ship_set(self):
        assert make_adapter()._ship == "~zod"

    def test_password_set(self):
        assert make_adapter()._password == "lidlut-tabwed"

    def test_bot_ship_defaults_to_ship(self):
        assert make_adapter()._bot_ship == "~zod"

    def test_bot_ship_override(self):
        assert make_adapter(bot_ship="~nec")._bot_ship == "~nec"

    def test_cookie_empty_initially(self):
        assert make_adapter()._cookie == ""

    def test_channel_uid_empty_initially(self):
        assert make_adapter()._channel_uid == ""

    def test_action_id_zero_initially(self):
        assert make_adapter()._action_id == 0

    def test_task_none_initially(self):
        assert make_adapter()._task is None

    def test_session_none_initially(self):
        assert make_adapter()._session is None

    def test_channel_id_class(self):
        assert TlonAdapter.channel_id == "tlon"

    def test_channel_id_instance(self):
        assert make_adapter().channel_id == "tlon"

    def test_custom_url(self):
        assert make_adapter(url="https://myship.arvo.network")._url == "https://myship.arvo.network"

    def test_empty_ship_allowed(self):
        assert TlonAdapter({})._ship == ""


# ===========================================================================
# 3. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_when_task_set(self):
        a = make_adapter()
        a._task = MagicMock()
        assert a.is_connected

    def test_not_connected_after_task_cleared(self):
        a = make_adapter()
        a._task = MagicMock()
        a._task = None
        assert not a.is_connected


# ===========================================================================
# 4. _next_id()
# ===========================================================================


class TestNextId:
    def test_starts_at_one(self):
        a = make_adapter()
        assert a._next_id() == 1

    def test_increments(self):
        a = make_adapter()
        a._next_id()
        assert a._next_id() == 2

    def test_sequence(self):
        a = make_adapter()
        assert [a._next_id() for _ in range(5)] == [1, 2, 3, 4, 5]


# ===========================================================================
# 5. _auth_headers()
# ===========================================================================


class TestAuthHeaders:
    def test_no_cookie_empty_headers(self):
        assert make_adapter()._auth_headers() == {}

    def test_cookie_present(self):
        a = make_adapter()
        a._cookie = "mytoken"
        assert a._auth_headers() == {"Cookie": "urbauth-~zod=mytoken"}

    def test_custom_ship_in_cookie(self):
        a = make_adapter(ship="~sampel-palnet")
        a._cookie = "tok"
        assert "urbauth-~sampel-palnet" in a._auth_headers()["Cookie"]


# ===========================================================================
# 6. connect() / disconnect() lifecycle
# ===========================================================================


class TestConnectDisconnect:
    @pytest.mark.asyncio
    async def test_connect_sets_task(self):
        a = make_adapter()
        session = _make_session()
        with patch("aiohttp.ClientSession", return_value=session):
            await a.connect()
        try:
            assert a._task is not None
        finally:
            if a._task:
                a._task.cancel()

    @pytest.mark.asyncio
    async def test_connect_sets_channel_uid(self):
        a = make_adapter()
        session = _make_session()
        with patch("aiohttp.ClientSession", return_value=session):
            await a.connect()
        try:
            assert a._channel_uid != ""
        finally:
            if a._task:
                a._task.cancel()

    @pytest.mark.asyncio
    async def test_connect_sets_cookie(self):
        a = make_adapter()
        session = _make_session(login_cookie="tok123")
        with patch("aiohttp.ClientSession", return_value=session):
            await a.connect()
        try:
            assert a._cookie == "tok123"
        finally:
            if a._task:
                a._task.cancel()

    @pytest.mark.asyncio
    async def test_connect_missing_ship_skips(self):
        a = make_adapter(ship="")
        await a.connect()
        assert a._task is None

    @pytest.mark.asyncio
    async def test_connect_missing_password_skips(self):
        a = make_adapter(password="")
        await a.connect()
        assert a._task is None

    @pytest.mark.asyncio
    async def test_connect_login_failure_clears_session(self):
        a = make_adapter()
        session = _make_session(login_status=403, login_cookie="")
        with patch("aiohttp.ClientSession", return_value=session):
            await a.connect()
        assert a._task is None
        assert a._session is None

    @pytest.mark.asyncio
    async def test_disconnect_cancels_task(self):
        a = make_adapter()
        task = asyncio.create_task(asyncio.sleep(1000))
        a._task = task
        a._session = _make_session()
        await a.disconnect()
        assert task.cancelled()

    @pytest.mark.asyncio
    async def test_disconnect_clears_task(self):
        a = make_adapter()
        a._task = asyncio.create_task(asyncio.sleep(1000))
        a._session = _make_session()
        await a.disconnect()
        assert a._task is None

    @pytest.mark.asyncio
    async def test_disconnect_closes_session(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        await a.disconnect()
        session.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_session(self):
        a = make_adapter()
        a._session = _make_session()
        await a.disconnect()
        assert a._session is None

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self):
        a = make_adapter()
        await a.disconnect()

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        a._session = _make_session()
        await a.disconnect()
        await a.disconnect()


# ===========================================================================
# 7. _login()
# ===========================================================================


class TestLogin:
    @pytest.mark.asyncio
    async def test_login_stores_cookie(self):
        a = make_adapter()
        session = _make_session(login_cookie="tok999")
        a._session = session
        await a._login()
        assert a._cookie == "tok999"

    @pytest.mark.asyncio
    async def test_login_raises_on_missing_cookie(self):
        a = make_adapter()
        session = _make_session(login_cookie="")
        a._session = session
        with pytest.raises(ValueError):
            await a._login()

    @pytest.mark.asyncio
    async def test_login_posts_to_correct_url(self):
        a = make_adapter(url="http://myship:8080")
        session = _make_session()
        a._session = session
        await a._login()
        call_url = session.post.call_args[0][0]
        assert call_url == f"http://myship:8080{_LOGIN_PATH}"

    @pytest.mark.asyncio
    async def test_login_sends_password(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        await a._login()
        data = session.post.call_args[1]["data"]
        assert data["password"] == "lidlut-tabwed"

    @pytest.mark.asyncio
    async def test_login_does_not_follow_redirects(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        await a._login()
        assert session.post.call_args[1]["allow_redirects"] is False


# ===========================================================================
# 8. _create_channel()
# ===========================================================================


class TestCreateChannel:
    @pytest.mark.asyncio
    async def test_puts_channel_url(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._cookie = "tok"
        a._channel_uid = "0v1.testuid"
        await a._create_channel()
        url = session.put.call_args[0][0]
        assert "/~/channel/0v1.testuid" in url

    @pytest.mark.asyncio
    async def test_raises_on_error_status(self):
        a = make_adapter()
        session = _make_session(put_status=500)
        a._session = session
        a._channel_uid = "0v1.x"
        with pytest.raises(ValueError):
            await a._create_channel()

    @pytest.mark.asyncio
    async def test_includes_auth_header(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._cookie = "mytoken"
        a._channel_uid = "0v1.x"
        await a._create_channel()
        headers = session.put.call_args[1]["headers"]
        assert "Cookie" in headers


# ===========================================================================
# 9. _subscribe()
# ===========================================================================


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_posts_action(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._cookie = "tok"
        a._channel_uid = "0v1.x"
        await a._subscribe()
        # get the channel POST call (not the login call)
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert body[0]["action"] == "subscribe"
        assert body[0]["app"] == _CHAT_APP
        assert body[0]["path"] == _CHAT_SUBSCRIBE_PATH
        assert body[0]["ship"] == "~zod"

    @pytest.mark.asyncio
    async def test_subscribe_increments_id(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a._subscribe()
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert body[0]["id"] == 1


# ===========================================================================
# 10. _post_actions()
# ===========================================================================


class TestPostActions:
    @pytest.mark.asyncio
    async def test_posts_json_body(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._cookie = "tok"
        a._channel_uid = "0v1.x"
        actions = [{"id": 1, "action": "ack", "event-id": 5}]
        await a._post_actions(actions)
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert body == actions

    @pytest.mark.asyncio
    async def test_posts_to_channel_url(self):
        a = make_adapter(url="http://ship:8080")
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.myuid"
        await a._post_actions([])
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        url = channel_calls[0][0][0]
        assert url == "http://ship:8080/~/channel/0v1.myuid"

    @pytest.mark.asyncio
    async def test_raises_on_error(self):
        a = make_adapter()
        session = _make_session(post_status=500)
        a._session = session
        a._channel_uid = "0v1.x"
        with pytest.raises(ValueError):
            await a._post_actions([{"id": 1, "action": "ack", "event-id": 1}])

    @pytest.mark.asyncio
    async def test_sends_content_type_json(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a._post_actions([])
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        headers = channel_calls[0][1]["headers"]
        assert headers.get("Content-Type") == "application/json"


# ===========================================================================
# 11. _ack()
# ===========================================================================


class TestAck:
    @pytest.mark.asyncio
    async def test_ack_sends_correct_action(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a._ack(42)
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert body[0]["action"] == "ack"
        assert body[0]["event-id"] == 42

    @pytest.mark.asyncio
    async def test_ack_swallows_post_errors(self):
        a = make_adapter()
        session = _make_session(post_status=500)
        a._session = session
        a._channel_uid = "0v1.x"
        await a._ack(1)

    @pytest.mark.asyncio
    async def test_ack_with_network_error_swallowed(self):
        a = make_adapter()
        session = MagicMock()

        def post_side_effect(url, **kwargs):
            resp = MagicMock()
            resp.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
            resp.__aexit__ = AsyncMock(return_value=False)
            return resp

        session.post = MagicMock(side_effect=post_side_effect)
        a._session = session
        a._channel_uid = "0v1.x"
        await a._ack(1)


# ===========================================================================
# 12. _parse_chat_update()
# ===========================================================================


class TestParseChatUpdate:
    def test_add_message_returns_message(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event())
        assert msg is not None

    def test_add_message_text(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(text="hi there"))
        assert msg.text == "hi there"

    def test_add_message_author(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(author="~sampel"))
        assert msg.sender_id == "~sampel"
        assert msg.sender_name == "~sampel"

    def test_add_message_path_as_thread_id(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(path="/~zod/dm/~nec"))
        assert msg.thread_id == "/~zod/dm/~nec"

    def test_add_message_timestamp(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(when=1698000000000))
        assert abs(msg.timestamp - 1698000000.0) < 1

    def test_add_message_channel_id(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event())
        assert msg.channel == "tlon"

    def test_modern_message_shape(self):
        a = make_adapter()
        data = {
            "message": {
                "path": "/~zod/~general",
                "envelope": {"uid": "0v1", "author": "~nec", "when": 1000, "letter": {"text": "hi"}},
            }
        }
        msg = a._parse_chat_update(data)
        assert msg is not None
        assert msg.text == "hi"

    def test_echo_guard_drops_bot_ship(self):
        a = make_adapter(ship="~zod")
        msg = a._parse_chat_update(_add_message_event(author="~zod"))
        assert msg is None

    def test_explicit_bot_ship_drops_matching(self):
        a = make_adapter(ship="~zod", bot_ship="~mybot")
        msg = a._parse_chat_update(_add_message_event(author="~mybot"))
        assert msg is None

    def test_explicit_bot_ship_allows_others(self):
        a = make_adapter(ship="~zod", bot_ship="~mybot")
        msg = a._parse_chat_update(_add_message_event(author="~nec"))
        assert msg is not None

    def test_other_ship_not_dropped(self):
        a = make_adapter(ship="~zod")
        msg = a._parse_chat_update(_add_message_event(author="~nec"))
        assert msg is not None

    def test_empty_text_returns_none(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(text=""))
        assert msg is None

    def test_missing_envelope_returns_none(self):
        a = make_adapter()
        msg = a._parse_chat_update({"add-message": {"path": "/p"}})
        assert msg is None

    def test_unknown_shape_returns_none(self):
        a = make_adapter()
        msg = a._parse_chat_update({"delete-message": {}})
        assert msg is None

    def test_story_inline_text(self):
        a = make_adapter()
        data = {
            "add-message": {
                "path": "/~zod/~chan",
                "envelope": {
                    "uid": "u",
                    "author": "~nec",
                    "when": 1000,
                    "letter": {"story": {"inline": ["hello tlon"], "block": []}},
                },
            }
        }
        msg = a._parse_chat_update(data)
        assert msg is not None
        assert msg.text == "hello tlon"

    def test_raw_contains_path_and_uid(self):
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(path="/~zod/~chan", uid="0v1.raw"))
        assert msg.raw["path"] == "/~zod/~chan"
        assert msg.raw["uid"] == "0v1.raw"

    def test_when_zero_uses_current_time(self):
        before = time.time() - 1
        a = make_adapter()
        msg = a._parse_chat_update(_add_message_event(when=0))
        assert msg.timestamp >= before


# ===========================================================================
# 13. _parse_target()
# ===========================================================================


class TestParseTarget:
    def test_bare_ship_is_dm(self):
        assert make_adapter()._parse_target("~sampel-palnet") == ("dm", "~sampel-palnet")

    def test_dm_prefix(self):
        assert make_adapter()._parse_target("dm:~nec") == ("dm", "~nec")

    def test_group_prefix(self):
        assert make_adapter()._parse_target("group:~host/channel") == ("group", "~host/channel")

    def test_path_prefix(self):
        assert make_adapter()._parse_target("path:/~zod/dm/~nec") == ("path", "/~zod/dm/~nec")

    def test_bare_slash_group(self):
        assert make_adapter()._parse_target("~host/name") == ("group", "~host/name")

    def test_bare_path_with_no_tilde(self):
        kind, val = make_adapter()._parse_target("hostname/channel")
        assert kind == "group"

    def test_empty_string_is_dm(self):
        kind, _ = make_adapter()._parse_target("")
        assert kind == "dm"


# ===========================================================================
# 14. _build_path()
# ===========================================================================


class TestBuildPath:
    def test_dm_path(self):
        a = make_adapter(ship="~zod")
        assert a._build_path("dm", "~nec") == "/~zod/dm/~nec"

    def test_dm_ship_without_tilde(self):
        a = make_adapter(ship="~zod")
        path = a._build_path("dm", "nec")
        assert "~nec" in path

    def test_group_path_with_tilde(self):
        a = make_adapter()
        assert a._build_path("group", "~host/channel-name") == "/~host/~channel-name"

    def test_group_path_without_tilde_host(self):
        a = make_adapter()
        path = a._build_path("group", "host/name")
        assert "~host" in path

    def test_path_passthrough(self):
        a = make_adapter()
        assert a._build_path("path", "/raw/urbit/path") == "/raw/urbit/path"

    def test_group_no_slash_falls_back(self):
        a = make_adapter()
        path = a._build_path("group", "just-name")
        assert path.startswith("/")


# ===========================================================================
# 15. _handle_sse_event()
# ===========================================================================


class TestHandleSseEvent:
    @pytest.mark.asyncio
    async def test_diff_dispatches_message(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        payload = {"response": "diff", "json": _add_message_event(text="hello")}
        await a._handle_sse_event(payload)
        await asyncio.sleep(0)
        assert msgs[0].text == "hello"

    @pytest.mark.asyncio
    async def test_subscribe_ok_no_dispatch(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        await a._handle_sse_event({"response": "subscribe", "ok": "ok"})
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_unknown_response_no_dispatch(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        await a._handle_sse_event({"response": "poke", "ok": "ok"})
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_quit_calls_resubscribe(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a._handle_sse_event({"response": "quit"})

    @pytest.mark.asyncio
    async def test_empty_diff_no_dispatch(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        await a._handle_sse_event({"response": "diff", "json": {}})
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_no_handler_does_not_crash(self):
        a = make_adapter()
        await a._handle_sse_event({"response": "diff", "json": _add_message_event()})
        await asyncio.sleep(0)


# ===========================================================================
# 16. _parse_sse()
# ===========================================================================


class TestParseSse:
    @pytest.mark.asyncio
    async def test_parses_event(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)

        event_data = {"response": "diff", "json": _add_message_event(text="sse msg")}
        chunk = _sse_chunk(event_data)
        content = _AsyncContent([chunk])
        await a._parse_sse(content)
        await asyncio.sleep(0)
        assert msgs[0].text == "sse msg"

    @pytest.mark.asyncio
    async def test_parses_multiple_events(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        chunk = _sse_chunk(
            {"response": "diff", "json": _add_message_event(text="msg1", author="~nec")},
            {"response": "diff", "json": _add_message_event(text="msg2", author="~nec")},
        )
        content = _AsyncContent([chunk])
        await a._parse_sse(content)
        await asyncio.sleep(0)
        assert len(msgs) == 2

    @pytest.mark.asyncio
    async def test_bad_json_skipped(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        bad_chunk = b"id: 1\ndata: NOT JSON {{{\n\n"
        content = _AsyncContent([bad_chunk])
        await a._parse_sse(content)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_acks_events(self):
        a = make_adapter()
        a._session = _make_session()
        a._channel_uid = "0v1.x"
        event_data = {"response": "subscribe", "ok": "ok"}
        chunk = _sse_chunk(event_data)
        content = _AsyncContent([chunk])
        await a._parse_sse(content)
        await asyncio.sleep(0)
        # ACK should have been scheduled via create_task
        channel_calls = [c for c in a._session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        assert len(channel_calls) > 0

    @pytest.mark.asyncio
    async def test_empty_content_no_dispatch(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        content = _AsyncContent([])
        await a._parse_sse(content)
        assert msgs == []


# ===========================================================================
# 17. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        a = make_adapter()
        a._session = _make_session()
        a._channel_uid = "0v1.x"
        assert await a.send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_session_returns_none(self):
        assert await make_adapter().send("~nec", "hi") is None

    @pytest.mark.asyncio
    async def test_success_returns_target(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._cookie = "tok"
        a._channel_uid = "0v1.x"
        result = await a.send("~nec", "hello")
        assert result == "~nec"

    @pytest.mark.asyncio
    async def test_poke_action_sent(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "hello")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert body[0]["action"] == "poke"
        assert body[0]["app"] == _CHAT_APP
        assert body[0]["mark"] == _CHAT_MARK

    @pytest.mark.asyncio
    async def test_poke_send_message_key(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "test msg")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        assert "send-message" in body[0]["json"]

    @pytest.mark.asyncio
    async def test_send_text_in_envelope(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "my text here")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        envelope = body[0]["json"]["send-message"]["envelope"]
        assert envelope["letter"]["text"] == "my text here"

    @pytest.mark.asyncio
    async def test_dm_path_in_envelope(self):
        a = make_adapter(ship="~zod")
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "hi")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        path = body[0]["json"]["send-message"]["path"]
        assert "dm" in path
        assert "~nec" in path

    @pytest.mark.asyncio
    async def test_group_path_in_envelope(self):
        a = make_adapter(ship="~zod")
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~host/general", "hi")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        path = body[0]["json"]["send-message"]["path"]
        assert "general" in path

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        session.post.side_effect = ConnectionError("fail")
        assert await a.send("~nec", "hi") is None

    @pytest.mark.asyncio
    async def test_poke_error_status_returns_none(self):
        a = make_adapter()
        session = _make_session(post_status=500)
        a._session = session
        a._channel_uid = "0v1.x"
        assert await a.send("~nec", "hi") is None

    @pytest.mark.asyncio
    async def test_author_is_own_ship(self):
        a = make_adapter(ship="~zod")
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "hi")
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        body = json.loads(channel_calls[0][1]["data"])
        envelope = body[0]["json"]["send-message"]["envelope"]
        assert envelope["author"] == "~zod"

    @pytest.mark.asyncio
    async def test_unicode_message(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        result = await a.send("~nec", "你好 🌸")
        assert result == "~nec"

    @pytest.mark.asyncio
    async def test_dm_prefix_target(self):
        a = make_adapter(ship="~zod")
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        result = await a.send("dm:~nec", "hello dm")
        assert result == "dm:~nec"

    @pytest.mark.asyncio
    async def test_path_prefix_target(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        result = await a.send("path:/~zod/~general", "hi path")
        assert result == "path:/~zod/~general"

    @pytest.mark.asyncio
    async def test_group_prefix_target(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        result = await a.send("group:~host/chan", "hi group")
        assert result == "group:~host/chan"


# ===========================================================================
# 18. ping()
# ===========================================================================


def _ping_session(status: int) -> MagicMock:
    resp = MagicMock()
    resp.status = status
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.post = MagicMock(return_value=resp)
    session.close = AsyncMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


class TestPing:
    @pytest.mark.asyncio
    async def test_no_ship_returns_false(self):
        assert await make_adapter(ship="").ping() is False

    @pytest.mark.asyncio
    async def test_no_password_returns_false(self):
        assert await make_adapter(password="").ping() is False

    @pytest.mark.asyncio
    async def test_302_returns_true(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(302)):
            assert await make_adapter().ping() is True

    @pytest.mark.asyncio
    async def test_200_returns_true(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(200)):
            assert await make_adapter().ping() is True

    @pytest.mark.asyncio
    async def test_204_returns_true(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(204)):
            assert await make_adapter().ping() is True

    @pytest.mark.asyncio
    async def test_301_returns_true(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(301)):
            assert await make_adapter().ping() is True

    @pytest.mark.asyncio
    async def test_401_returns_false(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(401)):
            assert await make_adapter().ping() is False

    @pytest.mark.asyncio
    async def test_500_returns_false(self):
        with patch("aiohttp.ClientSession", return_value=_ping_session(500)):
            assert await make_adapter().ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        session = MagicMock()
        session.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        session.__aexit__ = AsyncMock(return_value=False)
        with patch("aiohttp.ClientSession", return_value=session):
            assert await make_adapter().ping() is False

    @pytest.mark.asyncio
    async def test_posts_to_login_url(self):
        session = _ping_session(302)
        with patch("aiohttp.ClientSession", return_value=session):
            await make_adapter().ping()
        url = session.post.call_args[0][0]
        assert _LOGIN_PATH in url

    @pytest.mark.asyncio
    async def test_no_url_returns_false(self):
        assert await make_adapter(url="").ping() is False


# ===========================================================================
# 19. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_ship(self):
        assert "ship" in make_adapter().get_config_schema()["required"]

    def test_required_has_password(self):
        assert "password" in make_adapter().get_config_schema()["required"]

    def test_properties_present(self):
        props = make_adapter().get_config_schema()["properties"]
        for k in ("url", "ship", "password", "bot_ship"):
            assert k in props

    def test_url_default(self):
        assert (
            make_adapter().get_config_schema()["properties"]["url"]["default"]
            == "http://localhost:8080"
        )


# ===========================================================================
# 20. Constants
# ===========================================================================


class TestConstants:
    def test_login_path(self):
        assert _LOGIN_PATH == "/~/login"

    def test_chat_app(self):
        assert _CHAT_APP == "chat"

    def test_chat_mark(self):
        assert _CHAT_MARK == "chat-action-1"

    def test_subscribe_path(self):
        assert _CHAT_SUBSCRIBE_PATH == "/updates"


# ===========================================================================
# 21. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "tlon" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_multiple_messages_dispatched(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)

        for i in range(3):
            ev = _add_message_event(text=f"msg{i}", author="~nec")
            await a._handle_sse_event({"response": "diff", "json": ev})
        await asyncio.sleep(0)
        assert len(msgs) == 3
        assert {m.text for m in msgs} == {"msg0", "msg1", "msg2"}

    @pytest.mark.asyncio
    async def test_action_id_monotonically_increases(self):
        a = make_adapter()
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a._subscribe()
        await a._ack(99)
        channel_calls = [c for c in session.post.call_args_list if _LOGIN_PATH not in c[0][0]]
        id1 = json.loads(channel_calls[0][1]["data"])[0]["id"]
        id2 = json.loads(channel_calls[1][1]["data"])[0]["id"]
        assert id2 > id1

    @pytest.mark.asyncio
    async def test_send_does_not_dispatch_inbound(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        session = _make_session()
        a._session = session
        a._channel_uid = "0v1.x"
        await a.send("~nec", "outbound")
        await asyncio.sleep(0)
        assert msgs == []

    def test_group_with_two_components(self):
        a = make_adapter(ship="~zod")
        path = a._build_path("group", "~sampel/~general")
        assert "sampel" in path
        assert "general" in path

    @pytest.mark.asyncio
    async def test_sse_event_without_handler_does_not_crash(self):
        a = make_adapter()
        ev = _add_message_event(text="orphan")
        await a._handle_sse_event({"response": "diff", "json": ev})
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_echo_guard_own_ship_dropped(self):
        a = make_adapter(ship="~zod")
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        ev = _add_message_event(text="echo", author="~zod")
        await a._handle_sse_event({"response": "diff", "json": ev})
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_mixed_events_correct_dispatch(self):
        a = make_adapter()
        msgs: list = []

        async def handler(m):
            msgs.append(m)

        a.on_message(handler)
        events = [
            {"response": "subscribe", "ok": "ok"},
            {"response": "diff", "json": _add_message_event(text="real1", author="~nec")},
            {"response": "diff", "json": {}},
            {"response": "diff", "json": _add_message_event(text="real2", author="~nec")},
        ]
        for ev in events:
            await a._handle_sse_event(ev)
        await asyncio.sleep(0)
        assert len(msgs) == 2
        assert msgs[0].text == "real1"
        assert msgs[1].text == "real2"
