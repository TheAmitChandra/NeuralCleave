"""Viber channel adapter — REST API + webhook.

Viber is a VoIP/messaging app with 1 B+ installs, dominant in Eastern
Europe, South-East Asia, and the Middle East. The bot platform uses:

* **Webhook** for inbound messages (Viber POSTs to your URL).
* **REST API** (``chatapi.viber.com``) for outbound messages.

Inbound handling:
    Call ``handle_webhook(raw_body, signature)`` from your web framework
    (e.g., aiohttp route) to parse events and dispatch them to the
    registered handler. The gateway wires this via the ``/webhooks/viber``
    route registered in ``gateway/routes.py``.

    Supported event types: ``message`` (text, picture, video, file,
    contact, url, sticker, rich_media), ``subscribed``, ``conversation_started``.

Outbound:
    ``send(target, text)`` sends a Viber text message. *target* is the
    Viber user ID returned in inbound messages as ``sender.id``.

Setup::

    channels.viber.auth_token   = "ENV:VIBER_AUTH_TOKEN"
    channels.viber.webhook_url  = "https://yourdomain.com/webhooks/viber"
    channels.viber.bot_name     = "MyNeuralCleaveBot"
    channels.viber.bot_avatar   = ""                # optional URL

Security:
    Viber signs each webhook delivery with ``X-Viber-Content-Signature``:
    HMAC-SHA256(auth_token, raw_body). This adapter verifies the signature
    before dispatching; set ``verify_signature = false`` to disable.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from typing import Any

from neuralcleave.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_API_BASE = "https://chatapi.viber.com/pa"


class ViberAdapter(ChannelAdapter):
    """Viber bot adapter — REST send + webhook receive.

    Registers the bot's webhook on ``connect()`` and provides
    ``handle_webhook()`` for the gateway route to call.
    """

    channel_id = "viber"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._auth_token = self._resolve(config.get("auth_token", ""))
        self._webhook_url = str(config.get("webhook_url", ""))
        self._bot_name = str(config.get("bot_name", "NeuralCleaveBot"))
        self._bot_avatar = str(config.get("bot_avatar", ""))
        self._verify_sig = bool(config.get("verify_signature", True))
        self._bot_id: str = ""           # populated from set_webhook response
        self._connected: bool = False
        self._session: Any | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            import aiohttp  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aiohttp")

        if not self._auth_token:
            raise RuntimeError("ViberAdapter requires 'auth_token' in config")

        self._session = aiohttp.ClientSession()

        if self._webhook_url:
            await self._set_webhook()

        self._connected = True
        logger.info("viber.connected bot=%s", self._bot_name)

    async def disconnect(self) -> None:
        self._connected = False
        if self._session:
            await self._session.close()
            self._session = None
        logger.info("viber.disconnected bot=%s", self._bot_name)

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a text message to a Viber user.

        Args:
            target:  Viber user ID (from ``sender.id`` in inbound events).
            text:    Message text (max 7,000 characters).
        """
        if not self._session:
            return None

        payload: dict[str, Any] = {
            "receiver": target,
            "type": "text",
            "text": text[:7000],
            "sender": {"name": self._bot_name},
        }
        if self._bot_avatar:
            payload["sender"]["avatar"] = self._bot_avatar

        try:
            resp_data = await self._api_post("/send_message", payload)
            status = resp_data.get("status", -1)
            token = resp_data.get("message_token")
            if status != 0:
                logger.error("viber.send failed status=%s target=%s", status, target)
                return None
            logger.debug("viber.sent token=%s target=%s", token, target)
            return str(token) if token else None
        except Exception as exc:
            logger.error("viber.send error target=%s: %s", target, exc)
            return None

    async def ping(self) -> bool:
        """Return True when we can reach the Viber API."""
        if not self._session:
            return False
        try:
            data = await self._api_get("/get_account_info")
            return data.get("status", 1) == 0
        except Exception:
            return False

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["auth_token"],
            "properties": {
                "auth_token": {"type": "string", "description": "Viber bot auth token (ENV:VIBER_AUTH_TOKEN)."},
                "webhook_url": {"type": "string", "description": "Public HTTPS URL for Viber to POST events to."},
                "bot_name": {"type": "string", "default": "NeuralCleaveBot"},
                "bot_avatar": {"type": "string", "description": "Avatar image URL shown in Viber chats."},
                "verify_signature": {"type": "boolean", "default": True,
                                     "description": "Verify X-Viber-Content-Signature on inbound webhooks."},
            },
        }

    # ------------------------------------------------------------------
    # Webhook handler (called by the gateway route)
    # ------------------------------------------------------------------

    async def handle_webhook(self, raw_body: bytes, signature: str) -> bool:
        """Parse a Viber webhook event and dispatch to the registered handler.

        Args:
            raw_body:   Raw request body bytes.
            signature:  Value of ``X-Viber-Content-Signature`` header.

        Returns:
            ``True`` if the event was processed, ``False`` if the signature
            was invalid or the event type is not handled.
        """
        if self._verify_sig and not self._check_signature(raw_body, signature):
            logger.warning("viber.webhook signature mismatch")
            return False

        try:
            import json
            data = json.loads(raw_body)
        except Exception:
            return False

        event_type = data.get("event", "")

        if event_type == "message":
            msg = self._parse_message_event(data)
            if msg:
                await self._dispatch(msg)
                return True

        elif event_type in ("subscribed", "conversation_started"):
            sender = data.get("user") or data.get("sender") or {}
            logger.info(
                "viber.%s user_id=%s name=%s",
                event_type,
                sender.get("id", "?"),
                sender.get("name", "?"),
            )
            return True

        return False

    def _parse_message_event(self, data: dict[str, Any]) -> InboundMessage | None:
        sender = data.get("sender") or {}
        message = data.get("message") or {}
        msg_type = message.get("type", "")
        text = message.get("text", "")
        sender_id = sender.get("id", "")

        # For non-text types, derive a text description
        if not text:
            if msg_type == "picture":
                text = message.get("text") or "[image]"
            elif msg_type == "video":
                text = "[video]"
            elif msg_type == "file":
                text = f"[file: {message.get('file_name', '')}]"
            elif msg_type == "contact":
                contact = message.get("contact", {})
                text = f"[contact: {contact.get('name', '')} {contact.get('phone_number', '')}]"
            elif msg_type == "url":
                text = message.get("media", "[url]")
            elif msg_type == "sticker":
                text = "[sticker]"

        if not text and not sender_id:
            return None

        # Build attachments
        attachments: list[Attachment] = []
        if msg_type == "picture":
            attachments.append(Attachment(type="image", url=message.get("media")))
        elif msg_type == "video":
            attachments.append(Attachment(type="video", url=message.get("media")))
        elif msg_type == "file":
            attachments.append(Attachment(
                type="document",
                url=message.get("media"),
                filename=message.get("file_name"),
            ))

        return InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender.get("name", sender_id),
            text=text or None,
            attachments=attachments,
            thread_id=data.get("chat_hostname", sender_id),
            raw=data,
        )

    def _check_signature(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(
            self._auth_token.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    # ------------------------------------------------------------------
    # API helpers
    # ------------------------------------------------------------------

    async def _set_webhook(self) -> None:
        payload = {
            "url": self._webhook_url,
            "event_types": ["delivered", "seen", "failed", "subscribed",
                            "conversation_started", "message"],
            "send_name": True,
            "send_photo": True,
        }
        data = await self._api_post("/set_webhook", payload)
        status = data.get("status", -1)
        if status != 0:
            logger.warning("viber.set_webhook failed status=%s msg=%s", status, data.get("status_message", ""))
        else:
            logger.info("viber.webhook_set url=%s", self._webhook_url)

    async def _api_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "X-Viber-Auth-Token": self._auth_token,
            "Content-Type": "application/json",
        }
        url = f"{_API_BASE}{path}"
        async with self._session.post(url, json=payload, headers=headers, timeout=15) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _api_get(self, path: str) -> dict[str, Any]:
        headers = {"X-Viber-Auth-Token": self._auth_token}
        url = f"{_API_BASE}{path}"
        async with self._session.get(url, headers=headers, timeout=10) as resp:
            resp.raise_for_status()
            return await resp.json()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
