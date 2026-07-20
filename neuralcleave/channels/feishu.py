"""Feishu / Lark channel adapter — Feishu Open Platform bot.

CortexFlow registers as a Feishu/Lark app bot.  Feishu delivers events
to a registered webhook URL; this adapter runs a lightweight ``aiohttp``
server to receive them.  Outbound messages are sent via the Feishu IM
API using a short-lived tenant access token obtained from the configured
``app_id`` + ``app_secret``.

Both v1 (legacy schema) and v2 (``"schema": "2.0"``) event formats are
handled.

Authentication:
    ``app_id``            Feishu/Lark app ID — required for token fetch
                          and all outbound API calls.
    ``app_secret``        Feishu/Lark app secret — used together with
                          ``app_id`` to obtain a tenant access token.
    ``verification_token``  Token printed in the Feishu developer console
                          under *Event Subscriptions → Security Settings*.
                          When set, every inbound webhook body is checked
                          against it before processing.

Config keys:
    app_id              Feishu/Lark app ID (required for send / ping)
    app_secret          Feishu/Lark app secret (required for send / ping)
    verification_token  Optional inbound verification token
    host                Webhook server bind host (default: ``"0.0.0.0"``)
    port                Webhook server port (default: 8087)
    webhook_path        URL path (default: ``"/webhook/feishu"``)
    bot_open_id         Bot's ``open_id``; messages from this ID are
                        dropped to prevent echo loops
    receive_id_type     Recipient ID type for outbound messages:
                        ``"open_id"`` (default) | ``"chat_id"`` |
                        ``"user_id"`` | ``"union_id"``

Outbound target format:
    ``ou_<hex>``  User open_id — pair with ``receive_id_type="open_id"``
    ``oc_<hex>``  Group chat ID — pair with ``receive_id_type="chat_id"``

Example config.toml::

    [channels.feishu]
    enabled            = true
    app_id             = "ENV:FEISHU_APP_ID"
    app_secret         = "ENV:FEISHU_APP_SECRET"
    verification_token = "ENV:FEISHU_VERIFICATION_TOKEN"
    port               = 8087
    webhook_path       = "/webhook/feishu"
    bot_open_id        = ""
    receive_id_type    = "open_id"
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_FEISHU_API = "https://open.feishu.cn/open-apis"
_TOKEN_URL = f"{_FEISHU_API}/auth/v3/tenant_access_token/internal"
_SEND_URL = f"{_FEISHU_API}/im/v1/messages"
_BOT_INFO_URL = f"{_FEISHU_API}/bot/v3/info"

_VALID_RECEIVE_ID_TYPES = frozenset({"open_id", "chat_id", "user_id", "union_id"})


class FeishuAdapter(ChannelAdapter):
    """Feishu/Lark bot adapter — aiohttp webhook receiver + IM API sender."""

    channel_id = "feishu"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._app_id: str = config.get("app_id", "")
        self._app_secret: str = config.get("app_secret", "")
        self._verification_token: str = config.get("verification_token", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8087))
        self._webhook_path: str = config.get("webhook_path", "/webhook/feishu")
        self._bot_open_id: str = config.get("bot_open_id", "")
        receive_id_type = config.get("receive_id_type", "open_id")
        self._receive_id_type: str = (
            receive_id_type if receive_id_type in _VALID_RECEIVE_ID_TYPES else "open_id"
        )
        self._runner: Any = None
        self._cached_token: str | None = None
        self._token_expiry: float = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server to receive Feishu events."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get(self._webhook_path, self._handle_health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "feishu.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        """Stop the aiohttp webhook server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("feishu.disconnected")

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
        """Send a text message via the Feishu IM API.

        *target* is the recipient ID whose type is controlled by the
        ``receive_id_type`` config key (default: ``"open_id"``).

        Returns the Feishu ``message_id`` on success, ``None`` on error.
        """
        if not target:
            logger.warning("feishu.send: target is empty")
            return None

        token = await self._get_access_token()
        if not token:
            return None

        payload: dict[str, Any] = {
            "receive_id": target,
            "content": json.dumps({"text": text}),
            "msg_type": "text",
        }
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _SEND_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                    params={"receive_id_type": self._receive_id_type},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    logger.error("feishu.send_api_error: %s", data)
                    return None
                return data.get("data", {}).get("message_id")
        except Exception as exc:
            logger.error("feishu.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the configured credentials are valid.

        Obtains a tenant access token and calls ``GET /bot/v3/info``.
        Returns ``False`` if no credentials are configured, if the token
        fetch fails, or if the bot-info call returns a non-zero code.
        """
        token = await self._get_access_token()
        if not token:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _BOT_INFO_URL,
                    headers={"Authorization": f"Bearer {token}"},
                    timeout=5.0,
                )
                if resp.status_code != 200:
                    return False
                return resp.json().get("code") == 0
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Tenant access token
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str | None:
        """Fetch (or return cached) a Feishu tenant access token.

        Requires both ``app_id`` and ``app_secret`` to be configured.
        Caches the token until 60 seconds before its declared expiry.
        Returns ``None`` on any error.
        """
        if not self._app_id or not self._app_secret:
            logger.warning("feishu.token: app_id and app_secret are required")
            return None

        if self._cached_token and time.time() < self._token_expiry - 60:
            return self._cached_token

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _TOKEN_URL,
                    json={"app_id": self._app_id, "app_secret": self._app_secret},
                    timeout=10.0,
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("code") != 0:
                    logger.error("feishu.token_error code=%s msg=%s", data.get("code"), data.get("msg"))
                    return None
                self._cached_token = data["tenant_access_token"]
                self._token_expiry = time.time() + int(data.get("expire", 7200))
                logger.debug("feishu.token refreshed expire=%s", data.get("expire"))
                return self._cached_token
        except Exception as exc:
            logger.error("feishu.token_fetch_error: %s", exc)
            return None

    # ------------------------------------------------------------------
    # Token / request verification
    # ------------------------------------------------------------------

    def _verify_request(self, body: dict[str, Any]) -> bool:
        """Return True if the inbound event body passes token verification.

        When ``verification_token`` is not configured, all requests are
        accepted (permissive mode — useful during local development).

        The token location differs by schema version:
        - v1: ``body["token"]``
        - v2: ``body["header"]["token"]``
        """
        if not self._verification_token:
            return True

        # v1 schema: token at the top level
        if "token" in body:
            return body["token"] == self._verification_token

        # v2 schema: token nested inside "header"
        header: dict[str, Any] = body.get("header") or {}
        if "token" in header:
            return header["token"] == self._verification_token

        return False

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    async def _handle_webhook(self, request: Any) -> Any:
        """Receive and route an inbound Feishu webhook POST."""
        from aiohttp import web

        try:
            body: dict[str, Any] = await request.json()
        except Exception:
            return web.Response(status=400, text="Invalid JSON")

        # URL verification challenge (Feishu sends this when you first register)
        if body.get("type") == "url_verification":
            if self._verification_token and body.get("token") != self._verification_token:
                return web.Response(status=401, text="Unauthorized")
            return web.json_response({"challenge": body.get("challenge", "")})

        # Token verification for regular events
        if not self._verify_request(body):
            return web.Response(status=401, text="Unauthorized")

        # Route by schema version
        if body.get("schema") == "2.0":
            header: dict[str, Any] = body.get("header") or {}
            if header.get("event_type") == "im.message.receive_v1":
                await self._process_event_v2(body.get("event") or {})
        elif body.get("type") == "event_callback":
            event: dict[str, Any] = body.get("event") or {}
            if event.get("type") == "message":
                await self._process_event_v1(event)

        return web.Response(status=200, text="OK")

    async def _handle_health(self, request: Any) -> Any:
        """Respond to GET requests (Feishu webhook connectivity check)."""
        from aiohttp import web

        return web.Response(status=200, text="Feishu adapter OK")

    # ------------------------------------------------------------------
    # Event processing — v2 (schema 2.0)
    # ------------------------------------------------------------------

    async def _process_event_v2(self, event: dict[str, Any]) -> None:
        """Parse a Feishu v2 ``im.message.receive_v1`` event payload.

        Silently drops:
        - Non-text message types (image, file, audio, sticker, …)
        - Messages with empty or whitespace-only text
        - Messages from :attr:`_bot_open_id` (echo-loop prevention)
        """
        message: dict[str, Any] = event.get("message") or {}
        if message.get("message_type") != "text":
            return

        try:
            content: dict[str, Any] = json.loads(message.get("content") or "{}")
            text: str = (content.get("text") or "").strip()
        except Exception:
            return

        if not text:
            return

        sender: dict[str, Any] = event.get("sender") or {}
        sender_ids: dict[str, Any] = sender.get("sender_id") or {}
        open_id: str = sender_ids.get("open_id", "unknown")

        if self._bot_open_id and open_id == self._bot_open_id:
            return

        chat_id: str = message.get("chat_id", "")
        thread_id: str = chat_id or open_id

        raw_ts: Any = message.get("create_time") or str(int(time.time() * 1000))
        try:
            timestamp: float = int(raw_ts) / 1000.0
        except (ValueError, TypeError):
            timestamp = time.time()

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=open_id,
            sender_name=open_id,
            text=text,
            thread_id=thread_id,
            timestamp=timestamp,
            raw=event,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # Event processing — v1 (legacy)
    # ------------------------------------------------------------------

    async def _process_event_v1(self, event: dict[str, Any]) -> None:
        """Parse a Feishu v1 ``event_callback`` message event.

        Silently drops:
        - Messages with empty or whitespace-only text
        - Messages from :attr:`_bot_open_id` (echo-loop prevention)
        """
        text: str = (event.get("text") or "").strip()
        if not text:
            return

        open_id: str = event.get("open_id", "unknown")

        if self._bot_open_id and open_id == self._bot_open_id:
            return

        chat_id: str = event.get("open_chat_id", "")
        thread_id: str = chat_id or open_id

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=open_id,
            sender_name=open_id,
            text=text,
            thread_id=thread_id,
            timestamp=time.time(),
            raw=event,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["app_id", "app_secret"],
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "Feishu/Lark app ID",
                },
                "app_secret": {
                    "type": "string",
                    "description": "Feishu/Lark app secret",
                },
                "verification_token": {
                    "type": "string",
                    "description": "Token to verify inbound event authenticity",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8087,
                    "description": "Webhook server port",
                },
                "webhook_path": {
                    "type": "string",
                    "default": "/webhook/feishu",
                    "description": "URL path for the webhook endpoint",
                },
                "bot_open_id": {
                    "type": "string",
                    "description": "Bot's open_id; messages from this ID are ignored",
                },
                "receive_id_type": {
                    "type": "string",
                    "enum": ["open_id", "chat_id", "user_id", "union_id"],
                    "default": "open_id",
                    "description": "Recipient ID type for outbound messages",
                },
            },
        }
