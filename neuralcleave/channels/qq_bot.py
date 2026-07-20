"""QQ Bot channel adapter (QQ OpenAPI webhook + REST).

Connects CortexFlow to Tencent's QQ official bot platform.  Inbound
messages arrive via webhook (POST); outbound messages are sent through
the QQ OpenAPI REST interface using a short-lived OAuth2 access token.

Supported inbound event types
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
``AT_MESSAGE_CREATE``        @-mention in a guild channel
``C2C_MESSAGE_CREATE``       Direct message from a user (private chat)
``GROUP_AT_MESSAGE_CREATE``  @-mention inside a QQ group
``DIRECT_MESSAGE_CREATE``    Guild direct message

Authentication
^^^^^^^^^^^^^^
Short-lived access tokens (7200 s) are obtained from
``bots.qq.com/app/getAppAccessToken`` using ``app_id`` + ``client_secret``
and refreshed automatically 60 s before expiry.

Webhook signature
^^^^^^^^^^^^^^^^^
Each inbound POST carries ``X-Signature-Ed25519`` (hex) and
``X-Signature-Timestamp``.  Verified via
``HMAC-SHA256(client_secret, timestamp_bytes + body_bytes)``.

URL verification challenge (op 13)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
When QQ first verifies a webhook URL it sends
``{"op": 13, "d": {"plain_token": "…", "event_ts": "…"}}``.
The adapter responds with
``{"plain_token": "…", "signature": hex(HMAC-SHA256(client_secret, event_ts + plain_token))}``.

Config keys
^^^^^^^^^^^
app_id          QQ bot application ID (required)
client_secret   QQ bot client secret — used for HMAC and token fetch (required)
bot_openid      Bot's own openid; leading @-mention tags stripped from content;
                messages from this openid are dropped (optional)
host            Webhook server bind host (default ``"0.0.0.0"``)
port            Webhook server port (default 8093)
webhook_path    URL path for the webhook (default ``"/webhook/qq_bot"``)

Outbound target format
^^^^^^^^^^^^^^^^^^^^^^
``channel:{id}``   Guild text channel
``dm:{guild_id}``  Guild direct-message channel
``group:{openid}`` QQ group
``c2c:{openid}``   C2C (private) user message
``user:{openid}``  Alias for c2c:
Bare string        Treated as ``channel:{id}``

Example config.toml::

    [channels.qq_bot]
    enabled       = true
    app_id        = "ENV:QQ_APP_ID"
    client_secret = "ENV:QQ_CLIENT_SECRET"
    bot_openid    = "ENV:QQ_BOT_OPENID"
    port          = 8093
    webhook_path  = "/webhook/qq_bot"
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_APPTOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
_GUILD_API = "https://api.sgroup.qq.com"
_GROUP_API = "https://api.q.qq.com"
_OP_CHALLENGE = 13

_MSG_EVENTS = frozenset(
    {
        "AT_MESSAGE_CREATE",
        "C2C_MESSAGE_CREATE",
        "GROUP_AT_MESSAGE_CREATE",
        "DIRECT_MESSAGE_CREATE",
    }
)

_MENTION_RE = re.compile(r"<@!?\w+>")


def _strip_mentions(text: str) -> str:
    return _MENTION_RE.sub("", text).strip()


class QQBotAdapter(ChannelAdapter):
    """QQ Bot adapter — webhook receiver + QQ OpenAPI REST sender."""

    channel_id = "qq_bot"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._app_id: str = config.get("app_id", "")
        self._client_secret: str = config.get("client_secret", "")
        self._bot_openid: str = config.get("bot_openid", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8093))
        self._webhook_path: str = config.get("webhook_path", "/webhook/qq_bot")

        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get(self._webhook_path, self._handle_health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "qq_bot.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        """Stop the aiohttp webhook server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("qq_bot.disconnected")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Return a valid QQ Bot access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        if not self._app_id or not self._client_secret:
            return ""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _APPTOKEN_URL,
                    json={"appId": self._app_id, "clientSecret": self._client_secret},
                    timeout=10.0,
                )
                data = resp.json()
                new_token = data.get("access_token", "")
                if not new_token:
                    logger.error("qq_bot.token_error: %s", data)
                    return ""
                self._access_token = new_token
                expires_in = int(data.get("expires_in", "7200"))
                self._token_expires_at = time.time() + expires_in
                logger.info("qq_bot.token_refreshed expires_in=%d", expires_in)
                return self._access_token
        except Exception as exc:
            logger.error("qq_bot.token_refresh_error: %s", exc)
            return ""

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def _verify_signature(
        self, body: bytes, timestamp: str, sig_hex: str
    ) -> bool:
        """Verify HMAC-SHA256 webhook signature."""
        if not self._client_secret:
            return True
        if not sig_hex:
            return False
        msg = timestamp.encode() + body
        expected = hmac.new(
            self._client_secret.encode(), msg, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig_hex)

    def _make_challenge_response(self, plain_token: str, event_ts: str) -> str:
        """Compute the URL-verification challenge signature."""
        msg = (event_ts + plain_token).encode()
        sig = hmac.new(self._client_secret.encode(), msg, hashlib.sha256).hexdigest()
        return sig

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------

    async def _handle_webhook(self, request: Any) -> Any:
        """Handle inbound POST from QQ Bot platform."""
        from aiohttp import web

        sig_hex = request.headers.get("X-Signature-Ed25519", "")
        timestamp = request.headers.get("X-Signature-Timestamp", "")

        body = await request.read()

        if not self._verify_signature(body, timestamp, sig_hex):
            logger.warning("qq_bot.invalid_signature")
            return web.Response(status=401, text="Invalid signature")

        try:
            import json as _json

            payload = _json.loads(body)
        except Exception:
            return web.Response(status=400, text="Bad JSON")

        # URL verification challenge (op=13)
        op = payload.get("op")
        if op == _OP_CHALLENGE:
            d = payload.get("d", {})
            plain_token = d.get("plain_token", "")
            event_ts = d.get("event_ts", "")
            sig = self._make_challenge_response(plain_token, event_ts)
            import json as _json2

            return web.Response(
                content_type="application/json",
                text=_json2.dumps({"plain_token": plain_token, "signature": sig}),
            )

        event_type = payload.get("t", "")
        if event_type not in _MSG_EVENTS:
            return web.Response(text="ok")

        data = payload.get("d", {})
        sender_id, text, thread_id, msg_id = self._extract_message(event_type, data)

        if not text:
            return web.Response(text="ok")

        if self._bot_openid and sender_id == self._bot_openid:
            return web.Response(text="ok")

        try:
            ts = float(time.time())
            raw_ts = data.get("timestamp", "")
            if raw_ts:
                from datetime import datetime, timezone

                dt = datetime.fromisoformat(raw_ts)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                ts = dt.timestamp()
        except Exception:
            ts = time.time()

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=data.get("author", {}).get("username", sender_id),
            text=text,
            thread_id=thread_id,
            timestamp=ts,
            raw={"event_type": event_type, "data": data, "msg_id": msg_id},
        )

        import asyncio

        asyncio.create_task(self._dispatch(msg))
        logger.info("qq_bot.message_received type=%s sender=%s", event_type, sender_id)
        return web.Response(text="ok")

    def _extract_message(
        self, event_type: str, data: dict[str, Any]
    ) -> tuple[str, str, str, str]:
        """Return ``(sender_id, text, thread_id, msg_id)`` for a given event."""
        author = data.get("author", {})
        content = data.get("content", "").strip()
        msg_id = data.get("id", "")

        if event_type == "AT_MESSAGE_CREATE":
            sender_id = author.get("id", "")
            text = _strip_mentions(content)
            thread_id = data.get("channel_id", data.get("guild_id", ""))

        elif event_type == "DIRECT_MESSAGE_CREATE":
            sender_id = author.get("id", "")
            text = content
            thread_id = data.get("guild_id", "")

        elif event_type == "C2C_MESSAGE_CREATE":
            sender_id = author.get("user_openid", "")
            text = content
            thread_id = sender_id

        elif event_type == "GROUP_AT_MESSAGE_CREATE":
            sender_id = author.get("member_openid", "")
            text = _strip_mentions(content)
            thread_id = data.get("group_openid", "")

        else:
            sender_id = ""
            text = content
            thread_id = ""

        return sender_id, text, thread_id, msg_id

    async def _handle_health(self, request: Any) -> Any:
        """GET health check."""
        from aiohttp import web

        return web.Response(text="QQ Bot adapter OK")

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    def _parse_target(
        self, target: str
    ) -> tuple[str, str]:
        """Return ``(target_type, target_id)`` from a send target string."""
        for prefix in ("channel:", "dm:", "group:", "c2c:", "user:"):
            if target.startswith(prefix):
                kind = prefix.rstrip(":")
                if kind == "user":
                    kind = "c2c"
                return kind, target[len(prefix):]
        return "channel", target

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a text message to *target*.

        Returns the target string on success, ``None`` on error.
        """
        if not target:
            logger.warning("qq_bot.send: target is empty")
            return None

        token = await self._get_access_token()
        if not token:
            logger.error("qq_bot.send: no access token")
            return None

        kind, tid = self._parse_target(target)
        headers = {"Authorization": f"QQBot {token}", "Content-Type": "application/json"}

        if kind == "channel":
            url = f"{_GUILD_API}/channels/{tid}/messages"
            payload: dict[str, Any] = {"content": text, "msg_type": 0}
        elif kind == "dm":
            url = f"{_GUILD_API}/dms/{tid}/messages"
            payload = {"content": text, "msg_type": 0}
        elif kind == "group":
            url = f"{_GROUP_API}/v2/groups/{tid}/messages"
            payload = {"content": text, "msg_type": 0, "msg_seq": 1}
        elif kind == "c2c":
            url = f"{_GROUP_API}/v2/users/{tid}/messages"
            payload = {"content": text, "msg_type": 0, "msg_seq": 1}
        else:
            url = f"{_GUILD_API}/channels/{tid}/messages"
            payload = {"content": text, "msg_type": 0}

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload, headers=headers, timeout=15.0)
                if resp.status_code not in (200, 201):
                    logger.error(
                        "qq_bot.send_error target=%s status=%d body=%s",
                        target,
                        resp.status_code,
                        resp.text[:200],
                    )
                    return None
                return target
        except Exception as exc:
            logger.error("qq_bot.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if credentials are valid (access token can be fetched)."""
        if not self._app_id or not self._client_secret:
            return False
        token = await self._get_access_token()
        if not token:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_GUILD_API}/users/@me",
                    headers={"Authorization": f"QQBot {token}"},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["app_id", "client_secret"],
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "QQ bot application ID",
                },
                "client_secret": {
                    "type": "string",
                    "description": "QQ bot client secret (used for HMAC verification and token refresh)",
                },
                "bot_openid": {
                    "type": "string",
                    "description": "Bot's own openid (for mention-stripping and echo-loop prevention)",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8093,
                    "description": "Webhook server port",
                },
                "webhook_path": {
                    "type": "string",
                    "default": "/webhook/qq_bot",
                    "description": "URL path for the QQ Bot webhook endpoint",
                },
            },
        }
