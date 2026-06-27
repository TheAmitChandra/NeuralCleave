"""Webhook channel adapter — receive messages via HTTP POST.

A generic inbound HTTP receiver that turns POST requests into InboundMessages.
Useful for integrating custom apps, n8n/Zapier workflows, or any service that
can send an HTTP POST.

Request format (JSON body):
    {
        "sender_id":   "user-123",
        "sender_name": "Alice",              # optional
        "text":        "Hello from webhook",
        "thread_id":   "thread-abc",         # optional
        "secret":      "your-shared-secret"  # optional but recommended
    }

Response:
    {"status": "ok", "message_id": "<uuid>"}

Setup:
    pip install aiohttp>=3.9

    Required config:
        channels.webhook.port    = 7433           # port to listen on
        channels.webhook.path    = "/webhook"     # URL path
        channels.webhook.secret  = "ENV:WEBHOOK_SECRET"  # optional HMAC secret

Usage::

    adapter = WebhookAdapter({
        "port": 7433,
        "path": "/webhook",
        "secret": "my-secret",
    })
    adapter.on_message(my_handler)
    await adapter.connect()
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from typing import Any

from cortexflow.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class WebhookAdapter(ChannelAdapter):
    """HTTP POST webhook receiver that turns POSTs into InboundMessages.

    One of the simplest adapters — no external library dependency beyond aiohttp.
    Useful for generic integrations and n8n/Zapier/Zapier-like workflows.
    """

    channel_id = "webhook"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._port = int(config.get("port", 7433))
        self._path = str(config.get("path", "/webhook")).rstrip("/") or "/webhook"
        self._secret = self._resolve(config.get("secret", ""))
        self._host = str(config.get("host", "127.0.0.1"))
        self._site: Any | None = None
        self._runner: Any | None = None

    # ------------------------------------------------------------------
    # ChannelAdapter interface
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from aiohttp import web  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aiohttp>=3.9")

        app = web.Application()
        app.router.add_post(self._path, self._handle_post)
        app.router.add_get(self._path, self._handle_health)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._host, self._port)
        await self._site.start()
        logger.info(
            "webhook.connected host=%s port=%d path=%s",
            self._host,
            self._port,
            self._path,
        )

    async def disconnect(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        logger.info("webhook.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        # Webhook is inbound-only — no outbound send capability.
        # Return None to indicate unsupported.
        logger.debug("webhook.send is not supported for inbound-only webhook adapter")
        return None

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "default": 7433, "description": "Port to listen on."},
                "path": {"type": "string", "default": "/webhook", "description": "URL path for POST requests."},
                "host": {"type": "string", "default": "127.0.0.1", "description": "Bind address."},
                "secret": {"type": "string", "description": "Shared secret for HMAC validation (optional)."},
            },
        }

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def _handle_post(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import]

        # Validate HMAC signature if secret is configured
        if self._secret:
            signature = request.headers.get("X-Webhook-Signature", "")
            body = await request.read()
            if not self._valid_signature(body, signature):
                logger.warning("webhook.invalid_signature remote=%s", request.remote)
                return web.json_response({"error": "invalid signature"}, status=401)
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return web.json_response({"error": "invalid JSON"}, status=400)
        else:
            try:
                payload = await request.json()
            except Exception:
                return web.json_response({"error": "invalid JSON"}, status=400)

        sender_id = str(payload.get("sender_id", "anonymous"))
        sender_name = str(payload.get("sender_name", sender_id))
        text = str(payload.get("text", "")).strip()
        thread_id = payload.get("thread_id")

        if not text:
            return web.json_response({"error": "missing 'text' field"}, status=400)

        message_id = str(uuid.uuid4())
        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=thread_id,
            raw=payload,
        )

        if self._handler:
            asyncio.create_task(self._handler(msg))

        logger.info(
            "webhook.received sender=%s msg_id=%s len=%d",
            sender_id,
            message_id,
            len(text),
        )
        return web.json_response({"status": "ok", "message_id": message_id})

    async def _handle_health(self, request: Any) -> Any:
        from aiohttp import web  # type: ignore[import]

        return web.json_response({"status": "healthy", "channel": self.channel_id})

    # ------------------------------------------------------------------

    def _valid_signature(self, body: bytes, provided: str) -> bool:
        expected = hmac.new(
            self._secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, provided)

    @staticmethod
    def _resolve(value: str) -> str:
        """Expand ENV:VAR_NAME secrets."""
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
