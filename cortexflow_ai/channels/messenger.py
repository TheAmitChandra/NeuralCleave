"""Facebook Messenger channel adapter.

Uses Meta's Messenger Platform (Webhooks + Graph API v19.0).

The adapter receives inbound messages via a webhook (POST /webhook/messenger).
Outbound messages use the Graph API ``/me/messages`` endpoint.
HMAC-SHA256 signature verification is applied to each inbound POST when
``app_secret`` is configured (recommended for production).

Setup::

    1. Create a Meta Developer App at developers.facebook.com
    2. Add the "Messenger" product and link a Facebook Page
    3. Generate a Page Access Token (Settings → Messenger → Page Subscriptions)
    4. Subscribe the webhook callback URL and choose the 'messages' +
       'messaging_postbacks' + 'messaging_reads' fields
    5. Choose a verify_token (any string)

Config keys::

    channels.messenger.page_access_token = "ENV:FB_PAGE_ACCESS_TOKEN"
    channels.messenger.verify_token       = "ENV:FB_VERIFY_TOKEN"
    channels.messenger.app_secret         = "ENV:FB_APP_SECRET"   # optional, enables signature check
    channels.messenger.page_id            = "ENV:FB_PAGE_ID"       # echo-loop guard

Gateway endpoints::

    GET  /webhook/messenger   — Meta hub.challenge handshake (call verify_webhook())
    POST /webhook/messenger   — inbound messages (call handle_webhook())

Docs: https://developers.facebook.com/docs/messenger-platform
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_GRAPH_API = "https://graph.facebook.com/v19.0"


class MessengerAdapter(ChannelAdapter):
    """Facebook Messenger adapter using Meta Graph API webhooks.

    Inbound messages arrive via ``handle_webhook()``; outbound messages use
    ``send()``.  No long-running background task is started in ``connect()``
    because Meta pushes events via webhook rather than requiring a persistent
    connection.
    """

    channel_id = "messenger"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._token: str = self._resolve(config.get("page_access_token", ""))
        self._verify_token: str = self._resolve(config.get("verify_token", "cortexflow"))
        self._app_secret: str = self._resolve(config.get("app_secret", ""))
        self._page_id: str = self._resolve(config.get("page_id", ""))
        self._connected: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if not self._token:
            raise RuntimeError("Messenger page_access_token not configured")
        self._connected = True
        logger.info("MessengerAdapter connected page_id=%s", self._page_id or "<unknown>")

    async def disconnect(self) -> None:
        self._connected = False
        logger.info("MessengerAdapter disconnected")

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
        """Send a text message to the recipient PSID *target*.

        Returns the ``message_id`` on success, ``None`` on failure.
        ``reply_to`` and ``attachments`` are accepted but unused —
        Messenger does not have a threaded-reply primitive in the basic API.
        """
        if not self._token:
            return None

        payload: dict[str, Any] = {
            "recipient": {"id": target},
            "message": {"text": text},
            "messaging_type": "RESPONSE",
        }

        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{_GRAPH_API}/me/messages",
                    params={"access_token": self._token},
                    json=payload,
                    timeout=20.0,
                )
                resp.raise_for_status()
                data = resp.json()
            return data.get("message_id")
        except Exception as exc:
            logger.error("messenger.send failed target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Handle the GET hub.challenge handshake from Meta.

        Returns the *challenge* string if the *token* matches; ``None`` otherwise.
        """
        if mode == "subscribe" and token == self._verify_token:
            return challenge
        return None

    def verify_signature(self, body: bytes, signature_header: str) -> bool:
        """Verify ``X-Hub-Signature-256`` using ``app_secret``.

        Returns ``True`` if the signature is valid or if no ``app_secret`` is
        configured (permissive mode).  Callers should drop the request when this
        returns ``False``.
        """
        if not self._app_secret:
            return True
        if not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(
            self._app_secret.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_header[7:])

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process a verified POST /webhook/messenger payload."""
        if payload.get("object") != "page":
            return
        try:
            for entry in payload.get("entry", []):
                for event in entry.get("messaging", []):
                    await self._process_messaging_event(event)
        except Exception as exc:
            logger.warning("messenger.handle_webhook error: %s", exc)

    async def _process_messaging_event(self, event: dict[str, Any]) -> None:
        sender_id: str = event.get("sender", {}).get("id", "")
        recipient_id: str = event.get("recipient", {}).get("id", "")

        # Echo guard — skip messages sent by the page itself
        if self._page_id and sender_id == self._page_id:
            return
        if self._page_id and recipient_id != self._page_id:
            return

        ts_ms: int = event.get("timestamp", 0)
        timestamp: float = ts_ms / 1000.0 if ts_ms else time.time()

        msg = event.get("message")
        postback = event.get("postback")
        read_event = event.get("read")

        # Only dispatch text messages and postbacks
        if msg is not None:
            await self._process_message(sender_id, timestamp, msg, event)
        elif postback is not None:
            await self._process_postback(sender_id, timestamp, postback, event)
        elif read_event is not None:
            logger.debug("messenger.read_event sender=%s", sender_id)

    async def _process_message(
        self,
        sender_id: str,
        timestamp: float,
        msg: dict[str, Any],
        raw: dict[str, Any],
    ) -> None:
        text: str | None = msg.get("text")
        attachments: list[Attachment] = []

        for att in msg.get("attachments", []):
            att_type = att.get("type", "unknown")
            payload_data = att.get("payload", {})
            url = payload_data.get("url")
            attachments.append(Attachment(type=att_type, url=url))

        if not text and not attachments:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_id,  # display name requires a separate Graph API call
            text=text,
            attachments=attachments,
            timestamp=timestamp,
            raw=raw,
        )
        import asyncio
        asyncio.create_task(self._dispatch(inbound))

    async def _process_postback(
        self,
        sender_id: str,
        timestamp: float,
        postback: dict[str, Any],
        raw: dict[str, Any],
    ) -> None:
        title: str = postback.get("title", "")
        payload: str = postback.get("payload", "")
        text = f"{title}: {payload}" if (title and payload) else (title or payload)
        if not text:
            return

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_id,
            text=text,
            timestamp=timestamp,
            raw=raw,
        )
        import asyncio
        asyncio.create_task(self._dispatch(inbound))

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Probe the Graph API with the page access token."""
        if not self._token:
            return False
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{_GRAPH_API}/me",
                    params={"access_token": self._token, "fields": "id,name"},
                    timeout=10.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["page_access_token"],
            "properties": {
                "page_access_token": {
                    "type": "string",
                    "description": "Facebook Page Access Token (ENV:FB_PAGE_ACCESS_TOKEN)",
                },
                "verify_token": {
                    "type": "string",
                    "description": "Webhook verify token you configured in Meta App Dashboard",
                    "default": "cortexflow",
                },
                "app_secret": {
                    "type": "string",
                    "description": "App Secret for X-Hub-Signature-256 verification (ENV:FB_APP_SECRET)",
                },
                "page_id": {
                    "type": "string",
                    "description": "Facebook Page ID for echo-loop prevention (ENV:FB_PAGE_ID)",
                },
            },
        }
