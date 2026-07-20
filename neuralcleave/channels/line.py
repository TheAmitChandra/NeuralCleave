"""LINE channel adapter — LINE Messaging API webhook bot.

CortexFlow registers as a LINE Messaging API bot (webhook type).  LINE
delivers events to a configured HTTPS endpoint; this adapter runs a
lightweight ``aiohttp`` server to receive them.  Outbound messages are
sent via the LINE push-message API, which works at any time and is not
bound by the short-lived ``replyToken`` window.

Authentication:
    ``channel_access_token``  Bearer token for all outbound API calls.
                              Generate a long-lived token in the LINE
                              Developers Console.
    ``channel_secret``        Used to verify the ``X-Line-Signature``
                              header (HMAC-SHA256 of the raw request
                              body, base64-encoded) on every inbound
                              webhook request.

Config keys:
    channel_access_token  Bearer token for LINE Messaging API (required for send)
    channel_secret        Channel secret for signature verification (required)
    host                  Webhook server bind host (default: ``"0.0.0.0"``)
    port                  Webhook server port (default: 8086)
    webhook_path          URL path (default: ``"/webhook/line"``)
    bot_user_id           Bot's LINE ``userId``; messages from this ID are
                          dropped to prevent echo loops

Outbound target format:
    ``U<32 hex digits>``     Direct message to a LINE user
    ``C<32 hex digits>``     Group chat
    ``R<32 hex digits>``     Multi-person chat (room)

Example config.toml::

    [channels.line]
    enabled              = true
    channel_access_token = "ENV:LINE_CHANNEL_ACCESS_TOKEN"
    channel_secret       = "ENV:LINE_CHANNEL_SECRET"
    port                 = 8086
    webhook_path         = "/webhook/line"
    bot_user_id          = ""
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_LINE_API_BASE = "https://api.line.me/v2/bot"
_PUSH_URL = f"{_LINE_API_BASE}/message/push"
_INFO_URL = f"{_LINE_API_BASE}/info"


class LineAdapter(ChannelAdapter):
    """LINE Messaging API adapter — aiohttp webhook receiver + push sender."""

    channel_id = "line"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._token: str = config.get("channel_access_token", "")
        self._secret: str = config.get("channel_secret", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8086))
        self._webhook_path: str = config.get("webhook_path", "/webhook/line")
        self._bot_user_id: str = config.get("bot_user_id", "")
        self._runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server to receive LINE events."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get(self._webhook_path, self._handle_health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "line.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        """Stop the aiohttp webhook server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("line.disconnected")

    # ------------------------------------------------------------------
    # Outbound
    # ------------------------------------------------------------------

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a text message via the LINE push-message API.

        *target* is the LINE ``userId``, ``groupId``, or ``roomId``
        (whichever was set as ``thread_id`` on the inbound message).

        The LINE push API returns ``{}`` on success — no message ID is
        provided.  This method returns *target* on success so callers
        have a meaningful non-``None`` value to confirm the call went
        through, and ``None`` on any error.
        """
        if not self._token:
            logger.warning("line.send: no channel_access_token configured")
            return None
        if not target:
            logger.warning("line.send: target is empty")
            return None

        payload: dict[str, Any] = {
            "to": target,
            "messages": [{"type": "text", "text": text}],
        }
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _PUSH_URL,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._token}",
                        "Content-Type": "application/json",
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                return target
        except Exception as exc:
            logger.error("line.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the LINE channel access token is valid.

        Calls ``GET /v2/bot/info`` — returns 200 when the token is OK,
        401 when it is invalid or expired.
        """
        if not self._token:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _INFO_URL,
                    headers={"Authorization": f"Bearer {self._token}"},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Signature verification
    # ------------------------------------------------------------------

    def _verify_signature(self, body: bytes, signature: str) -> bool:
        """Verify the ``X-Line-Signature`` HMAC-SHA256 header.

        Computes ``base64(HMAC-SHA256(channel_secret, raw_body))`` and
        compares it to *signature* using a constant-time compare.

        Returns ``False`` if no ``channel_secret`` is configured, if
        *signature* is empty, or if the digest does not match.
        """
        if not self._secret:
            return False
        if not signature:
            return False
        try:
            mac = hmac.new(
                self._secret.encode("utf-8"),
                body,
                hashlib.sha256,
            ).digest()
            expected = base64.b64encode(mac).decode()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    async def _handle_webhook(self, request: Any) -> Any:
        """Receive and route a LINE webhook POST request."""
        from aiohttp import web

        body: bytes = await request.read()
        signature: str = request.headers.get("X-Line-Signature", "")

        if self._secret:
            if not self._verify_signature(body, signature):
                logger.warning("line.invalid_signature")
                return web.Response(status=400, text="Bad signature")

        try:
            data: dict[str, Any] = json.loads(body)
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        events: list[dict[str, Any]] = data.get("events") or []
        for event in events:
            await self._process_event(event)

        return web.Response(status=200, text="OK")

    async def _handle_health(self, request: Any) -> Any:
        """Respond to GET requests (LINE webhook verification)."""
        from aiohttp import web

        return web.Response(status=200, text="LINE adapter OK")

    # ------------------------------------------------------------------
    # Event processing
    # ------------------------------------------------------------------

    async def _process_event(self, event: dict[str, Any]) -> None:
        """Parse a LINE event dict and dispatch an :class:`InboundMessage`.

        Silently drops:
        - Non-``message`` event types (follow, unfollow, join, leave,
          postback, beacon, memberJoined, memberLeft, …)
        - Non-``text`` message subtypes (image, sticker, video, audio,
          location, file, template, flex, …)
        - Messages with empty or whitespace-only text
        - Messages whose ``userId`` matches :attr:`_bot_user_id`
        """
        if event.get("type") != "message":
            return

        message: dict[str, Any] = event.get("message") or {}
        if message.get("type") != "text":
            return

        text: str = (message.get("text") or "").strip()
        if not text:
            return

        source: dict[str, Any] = event.get("source") or {}
        source_type: str = source.get("type", "user")
        user_id: str = source.get("userId", "unknown")

        if self._bot_user_id and user_id == self._bot_user_id:
            return

        if source_type == "group":
            thread_id: str = source.get("groupId", user_id)
        elif source_type == "room":
            thread_id = source.get("roomId", user_id)
        else:
            thread_id = user_id

        raw_ts: int | float = event.get("timestamp", int(time.time() * 1000))
        timestamp: float = raw_ts / 1000.0

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=user_id,
            sender_name=user_id,
            text=text,
            thread_id=thread_id,
            timestamp=timestamp,
            raw=event,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["channel_access_token", "channel_secret"],
            "properties": {
                "channel_access_token": {
                    "type": "string",
                    "description": "LINE channel access token for outbound API calls",
                },
                "channel_secret": {
                    "type": "string",
                    "description": "LINE channel secret for webhook signature verification",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8086,
                    "description": "Webhook server port",
                },
                "webhook_path": {
                    "type": "string",
                    "default": "/webhook/line",
                    "description": "URL path for the LINE webhook endpoint",
                },
                "bot_user_id": {
                    "type": "string",
                    "description": "Bot's LINE userId; messages from this ID are ignored",
                },
            },
        }
