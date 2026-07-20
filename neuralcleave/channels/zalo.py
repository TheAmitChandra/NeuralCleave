"""Zalo Official Account (OA) channel adapter.

Zalo is Vietnam's dominant messaging platform.  This adapter connects
CortexFlow to a Zalo Official Account via:

1. **Outgoing webhook receiver** — an ``aiohttp`` server that Zalo POSTs to
   whenever a user sends a message to the OA.  The adapter verifies the
   HMAC-SHA256 ``X-ZAlo-Signature`` header before dispatching an
   ``InboundMessage``.

2. **Customer-service message sender** — uses the Zalo OA v3 Customer Service
   Message API to reply to users.  Requires a valid access token obtained by
   exchanging the configured ``refresh_token``.

Authentication:
    ``app_id``          Zalo application ID (required)
    ``app_secret``      Zalo application secret (required)
    ``refresh_token``   Long-lived refresh token from the Zalo OAuth flow
                        (required for send and ping)

Token lifecycle:
    Access tokens expire after 3600 s.  The adapter refreshes them
    automatically (60 s before expiry) using the stored refresh token.
    A successful refresh also updates ``refresh_token`` in-memory if Zalo
    returns a new one.

Config keys:
    app_id          Zalo application ID (required)
    app_secret      Zalo application secret; used for HMAC verification and
                    token refresh (required)
    refresh_token   Initial refresh token from the Zalo OA dashboard (required
                    for send / ping)
    bot_oa_id       The OA's own Zalo user ID; messages from this ID are
                    dropped to prevent echo loops
    host            Webhook server bind host (default: ``"0.0.0.0"``)
    port            Webhook server port (default: 8091)
    webhook_path    URL path for the webhook endpoint (default:
                    ``"/webhook/zalo"``)

Outbound target format:
    Zalo ``user_id_by_app`` (the per-OA user ID returned in webhook events).

Example config.toml::

    [channels.zalo]
    enabled       = true
    app_id        = "ENV:ZALO_APP_ID"
    app_secret    = "ENV:ZALO_APP_SECRET"
    refresh_token = "ENV:ZALO_REFRESH_TOKEN"
    bot_oa_id     = "ENV:ZALO_OA_ID"
    port          = 8091
    webhook_path  = "/webhook/zalo"
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_TOKEN_URL = "https://oauth.zaloapp.com/v4/oa/access_token"
_SEND_URL = "https://openapi.zalo.me/v3.0/oa/message/cs"
_OA_INFO_URL = "https://openapi.zalo.me/v2.0/oa/info"


class ZaloAdapter(ChannelAdapter):
    """Zalo OA adapter — webhook receiver + CS message sender."""

    channel_id = "zalo"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._app_id: str = config.get("app_id", "")
        self._app_secret: str = config.get("app_secret", "")
        self._refresh_token: str = config.get("refresh_token", "")
        self._bot_oa_id: str = config.get("bot_oa_id", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8091))
        self._webhook_path: str = config.get("webhook_path", "/webhook/zalo")

        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._runner: Any = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server to receive Zalo OA events."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_webhook)
        app.router.add_get(self._webhook_path, self._handle_health)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "zalo.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        """Stop the aiohttp webhook server."""
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("zalo.disconnected")

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    async def _get_access_token(self) -> str:
        """Return a valid access token, refreshing if needed."""
        if self._access_token and time.time() < self._token_expires_at - 60:
            return self._access_token
        if not self._refresh_token or not self._app_id or not self._app_secret:
            return ""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _TOKEN_URL,
                    data={
                        "app_id": self._app_id,
                        "grant_type": "refresh_token",
                        "refresh_token": self._refresh_token,
                    },
                    headers={"secret_key": self._app_secret},
                    timeout=10.0,
                )
                data = resp.json()
                new_token = data.get("access_token", "")
                if not new_token:
                    logger.error("zalo.token_refresh_failed: %s", data)
                    return ""
                self._access_token = new_token
                expires_in = int(data.get("expires_in", 3600))
                self._token_expires_at = time.time() + expires_in
                new_refresh = data.get("refresh_token", "")
                if new_refresh:
                    self._refresh_token = new_refresh
                logger.info("zalo.token_refreshed expires_in=%d", expires_in)
                return self._access_token
        except Exception as exc:
            logger.error("zalo.token_refresh_error: %s", exc)
            return ""

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
        """Send a Customer Service text message to *target* (``user_id_by_app``).

        Returns the target on success, ``None`` on error.
        """
        if not target:
            logger.warning("zalo.send: target is empty")
            return None

        token = await self._get_access_token()
        if not token:
            logger.error("zalo.send: no access token")
            return None

        try:
            import httpx

            payload = {
                "recipient": {"user_id": target},
                "message": {"text": text},
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _SEND_URL,
                    json=payload,
                    headers={"access_token": token},
                    timeout=15.0,
                )
                data = resp.json()
                if data.get("error") != 0:
                    logger.error("zalo.send_error target=%s: %s", target, data)
                    return None
                return target
        except Exception as exc:
            logger.error("zalo.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if credentials are valid and the OA info endpoint responds."""
        try:
            token = await self._get_access_token()
            if not token:
                return False
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    _OA_INFO_URL,
                    headers={"access_token": token},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    def _verify_signature(self, body: bytes, sig_header: str) -> bool:
        """Verify Zalo HMAC-SHA256 ``X-ZAlo-Signature`` header."""
        if not self._app_secret or not sig_header:
            return not self._app_secret
        expected = hmac.new(
            self._app_secret.encode(), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, sig_header)

    async def _handle_webhook(self, request: Any) -> Any:
        """Receive a Zalo OA webhook event POST."""
        from aiohttp import web

        body = await request.read()
        sig = request.headers.get("X-ZAlo-Signature", "")

        if not self._verify_signature(body, sig):
            logger.warning("zalo.invalid_signature")
            return web.Response(status=401, text="Unauthorized")

        try:
            import json as _json

            event = _json.loads(body)
        except Exception:
            return web.Response(status=400, text="Bad request")

        event_name = event.get("event_name", "")
        if event_name not in (
            "user_send_text",
            "user_send_image",
            "user_send_sticker",
            "user_send_file",
            "user_send_audio",
            "user_send_video",
        ):
            return web.Response(status=200, text="OK")

        sender = event.get("sender", {})
        recipient = event.get("recipient", {})
        message = event.get("message", {})

        sender_id = event.get("user_id_by_app") or sender.get("id", "")
        oa_id = recipient.get("id", "")

        if self._bot_oa_id and sender_id == self._bot_oa_id:
            return web.Response(status=200, text="OK")

        text = message.get("text", "").strip()
        if event_name != "user_send_text":
            text = text or f"[{event_name}]"

        if not text:
            return web.Response(status=200, text="OK")

        try:
            ts = float(event.get("timestamp", time.time()))
        except (TypeError, ValueError):
            ts = time.time()

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender.get("display_name", sender_id),
            text=text,
            thread_id=oa_id or sender_id,
            timestamp=ts,
            raw=event,
        )

        import asyncio

        asyncio.create_task(self._dispatch(msg))
        logger.info(
            "zalo.message_received sender=%s event=%s",
            sender_id,
            event_name,
        )
        return web.Response(status=200, text="OK")

    async def _handle_health(self, request: Any) -> Any:
        """Respond to GET requests (Zalo webhook URL verification / health check)."""
        from aiohttp import web

        return web.Response(status=200, text="Zalo adapter OK")

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["app_id", "app_secret", "refresh_token"],
            "properties": {
                "app_id": {
                    "type": "string",
                    "description": "Zalo application ID",
                },
                "app_secret": {
                    "type": "string",
                    "description": "Zalo application secret (used for HMAC verification and token refresh)",
                },
                "refresh_token": {
                    "type": "string",
                    "description": "Long-lived Zalo OA refresh token",
                },
                "bot_oa_id": {
                    "type": "string",
                    "description": "OA's own Zalo user ID (for echo-loop prevention)",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8091,
                    "description": "Webhook server port",
                },
                "webhook_path": {
                    "type": "string",
                    "default": "/webhook/zalo",
                    "description": "URL path for the Zalo OA webhook endpoint",
                },
            },
        }
