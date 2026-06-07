"""WhatsApp Cloud API channel adapter.

Uses Meta's official WhatsApp Business Cloud API — no browser automation,
no unofficial libraries, no QR code scanning. Works with any Meta Business
Account (free tier available with 1,000 conversations/month).

Setup:
    1. Create a Meta Developer App at developers.facebook.com
    2. Enable WhatsApp → set up a test phone number
    3. Copy the Phone Number ID and Permanent Token

    Required config:
        channels.whatsapp.phone_number_id = "ENV:WA_PHONE_NUMBER_ID"
        channels.whatsapp.access_token    = "ENV:WA_ACCESS_TOKEN"
        channels.whatsapp.verify_token    = "ENV:WA_VERIFY_TOKEN"  # webhook verify

    The gateway exposes POST /webhook/whatsapp for incoming messages.
    Register this URL in the Meta App Dashboard.

Docs: https://developers.facebook.com/docs/whatsapp/cloud-api
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import httpx

from cortexflow.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_API_BASE = "https://graph.facebook.com/v19.0"


class WhatsAppAdapter(ChannelAdapter):
    """WhatsApp Cloud API adapter.

    Inbound messages arrive via a webhook (POST /webhook/whatsapp).
    The gateway must call ``adapter.handle_webhook(payload)`` for each
    verified webhook event.  Outbound messages use the Cloud API REST endpoint.

    Because WhatsApp uses a push webhook model (not a long-poll), there is no
    background task to start in ``connect()``; the adapter simply validates
    its credentials and registers itself for webhook dispatch.
    """

    channel_id = "whatsapp"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._phone_number_id = self._resolve(config.get("phone_number_id", ""))
        self._access_token = self._resolve(config.get("access_token", ""))
        self._verify_token = self._resolve(config.get("verify_token", "cortexflow"))

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if not self._phone_number_id:
            raise RuntimeError("WhatsApp phone_number_id not configured")
        if not self._access_token:
            raise RuntimeError("WhatsApp access_token not configured")

        # Smoke-test the token by fetching our own phone number object
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{_API_BASE}/{self._phone_number_id}",
                headers=self._auth_headers(),
                timeout=10.0,
            )
            if resp.status_code == 401:
                raise RuntimeError("WhatsApp access_token is invalid")
            resp.raise_for_status()

        logger.info(
            "WhatsAppAdapter connected phone_number_id=%s", self._phone_number_id
        )

    async def disconnect(self) -> None:
        logger.info("WhatsAppAdapter disconnected")

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": target,
        }

        if reply_to:
            payload["context"] = {"message_id": reply_to}

        if attachments:
            att = attachments[0]
            media_type = att.type  # "image" | "audio" | "video" | "document"
            if media_type in ("image", "audio", "video", "document"):
                payload["type"] = media_type
                payload[media_type] = {"link": att.url, "caption": text if media_type == "image" else ""}
            else:
                payload["type"] = "text"
                payload["text"] = {"body": text, "preview_url": False}
        else:
            payload["type"] = "text"
            payload["text"] = {"body": text, "preview_url": False}

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_API_BASE}/{self._phone_number_id}/messages",
                headers=self._auth_headers(),
                json=payload,
                timeout=20.0,
            )
            resp.raise_for_status()
            data = resp.json()

        messages = data.get("messages", [])
        return messages[0].get("id") if messages else None

    # ------------------------------------------------------------------
    # Webhook handling
    # ------------------------------------------------------------------

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """Handle GET /webhook/whatsapp — return challenge if token matches."""
        if mode == "subscribe" and token == self._verify_token:
            return challenge
        return None

    async def handle_webhook(self, payload: dict[str, Any]) -> None:
        """Process a verified POST /webhook/whatsapp payload."""
        try:
            for entry in payload.get("entry", []):
                for change in entry.get("changes", []):
                    value = change.get("value", {})
                    await self._process_value(value)
        except Exception as exc:
            logger.warning("WhatsApp webhook processing error: %s", exc)

    async def _process_value(self, value: dict[str, Any]) -> None:
        contacts = {c["wa_id"]: c.get("profile", {}).get("name", c["wa_id"]) for c in value.get("contacts", [])}

        for msg in value.get("messages", []):
            sender_id = msg.get("from", "")
            sender_name = contacts.get(sender_id, sender_id)
            msg_type = msg.get("type", "text")
            text: str | None = None
            attachments: list[Attachment] = []

            if msg_type == "text":
                text = msg.get("text", {}).get("body")
            elif msg_type in ("image", "audio", "video", "document", "sticker"):
                media = msg.get(msg_type, {})
                attachments = [
                    Attachment(
                        type=msg_type if msg_type != "sticker" else "image",
                        url=None,  # must be fetched separately via media ID
                        filename=media.get("filename"),
                        mime_type=media.get("mime_type"),
                        data=None,
                    )
                ]
                text = media.get("caption")
            elif msg_type == "interactive":
                # Button reply or list reply
                interactive = msg.get("interactive", {})
                if interactive.get("type") == "button_reply":
                    text = interactive["button_reply"].get("title")
                elif interactive.get("type") == "list_reply":
                    text = interactive["list_reply"].get("title")

            inbound = InboundMessage(
                channel=self.channel_id,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                attachments=attachments,
                raw=msg,
            )
            await self._dispatch(inbound)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}"}

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "phone_number_id": {"type": "string", "description": "Meta WhatsApp Phone Number ID"},
                "access_token": {"type": "string", "description": "Meta permanent user access token"},
                "verify_token": {"type": "string", "description": "Webhook verify token (you choose)"},
            },
            "required": ["phone_number_id", "access_token"],
        }
