"""SMS channel adapter via Twilio.

Receives inbound SMS via Twilio webhook (TwiML) and sends replies via
Twilio's Messaging API.

Setup:
    pip install twilio>=8.0.0

    Required config:
        channels.sms.account_sid    = "ENV:TWILIO_ACCOUNT_SID"
        channels.sms.auth_token     = "ENV:TWILIO_AUTH_TOKEN"
        channels.sms.from_number    = "+15005550006"   # your Twilio number
        channels.sms.webhook_port   = 7434             # port for Twilio webhook
        channels.sms.webhook_path   = "/sms/inbound"

    In Twilio console, set webhook URL to:
        http://<your-host>:7434/sms/inbound

Usage::

    adapter = SMSAdapter({
        "account_sid": "AC...",
        "auth_token": "...",
        "from_number": "+15005550006",
    })
    adapter.on_message(my_handler)
    await adapter.connect()
    # Send to a phone number
    await adapter.send("+14155551234", "Hello from NeuralCleave!")
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neuralcleave.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class SMSAdapter(ChannelAdapter):
    """Twilio SMS adapter — receive via webhook, send via REST API.

    Inbound messages come from Twilio's webhook (POST to your server).
    Outbound messages are sent via the Twilio Messaging API.
    """

    channel_id = "sms"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._account_sid = self._resolve(config.get("account_sid", ""))
        self._auth_token = self._resolve(config.get("auth_token", ""))
        self._from_number = str(config.get("from_number", ""))
        self._webhook_port = int(config.get("webhook_port", 7434))
        self._webhook_path = str(config.get("webhook_path", "/sms/inbound"))
        self._webhook_host = str(config.get("webhook_host", "127.0.0.1"))
        self._runner: Any | None = None
        self._site: Any | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from aiohttp import web  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aiohttp>=3.9")

        app = web.Application()
        app.router.add_post(self._webhook_path, self._handle_inbound)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self._webhook_host, self._webhook_port)
        await self._site.start()
        logger.info(
            "sms.connected host=%s port=%d path=%s",
            self._webhook_host,
            self._webhook_port,
            self._webhook_path,
        )

    async def disconnect(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None
            self._site = None
        logger.info("sms.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Send an SMS to *target* (E.164 phone number, e.g. '+14155551234')."""
        try:
            from twilio.rest import Client  # type: ignore[import]
        except ImportError:
            logger.error("sms.send failed: pip install twilio")
            return None

        try:
            # Twilio client is synchronous; run in thread to avoid blocking event loop
            client = Client(self._account_sid, self._auth_token)
            loop = asyncio.get_running_loop()
            message = await loop.run_in_executor(
                None,
                lambda: client.messages.create(
                    body=text,
                    from_=self._from_number,
                    to=target,
                ),
            )
            logger.info("sms.sent to=%s sid=%s", target, message.sid)
            return message.sid
        except Exception as exc:
            logger.error("sms.send failed to=%s: %s", target, exc)
            return None

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["account_sid", "auth_token", "from_number"],
            "properties": {
                "account_sid": {"type": "string", "description": "Twilio Account SID (ENV:TWILIO_ACCOUNT_SID)."},
                "auth_token": {"type": "string", "description": "Twilio Auth Token (ENV:TWILIO_AUTH_TOKEN)."},
                "from_number": {"type": "string", "description": "Your Twilio phone number in E.164 format."},
                "webhook_port": {"type": "integer", "default": 7434},
                "webhook_path": {"type": "string", "default": "/sms/inbound"},
            },
        }

    # ------------------------------------------------------------------
    # Webhook handler
    # ------------------------------------------------------------------

    async def _handle_inbound(self, request: Any) -> Any:
        """Handle Twilio webhook POST — parse TwiML form data."""
        from aiohttp import web  # type: ignore[import]

        data = await request.post()
        sender_id = str(data.get("From", "unknown"))
        body = str(data.get("Body", "")).strip()
        sms_sid = str(data.get("SmsSid", ""))

        if not body:
            return web.Response(text="<Response/>", content_type="application/xml")

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_id,  # phone number as display name
            text=body,
            raw=dict(data),
        )

        if self._handler:
            asyncio.create_task(self._handler(msg))

        logger.info("sms.received from=%s sid=%s len=%d", sender_id, sms_sid, len(body))
        # Return empty TwiML — replies are sent separately via send()
        return web.Response(text="<Response/>", content_type="application/xml")

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
