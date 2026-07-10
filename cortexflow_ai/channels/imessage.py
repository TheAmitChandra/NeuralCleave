"""iMessage channel adapter — BlueBubbles server bridge.

CortexFlow connects to a self-hosted `BlueBubbles <https://bluebubbles.app>`_
server running on macOS. The server exposes a REST API and Socket.IO endpoint;
this adapter uses REST polling for inbound messages and the REST API for
outbound sending.

Authentication:
    The BlueBubbles server password is passed as the ``password`` query
    parameter on every API request.

Config keys:
    server_url      Base URL of your BlueBubbles server
                    (default: ``http://localhost:1234``)
    password        BlueBubbles server password (required)
    poll_interval   Seconds between inbound-message polls (default: 5.0)
    method          Send method: ``"apple-script"`` (default) or
                    ``"private-api"`` (requires Private API helper)
    bot_handle      Your Apple ID / phone number; messages from this handle
                    are skipped to prevent echo loops

Outbound target format:
    ``iMessage;-;+15551234567``          Direct iMessage to a phone number
    ``iMessage;-;user@example.com``      Direct iMessage to an Apple ID
    ``SMS;-;+15551234567``               SMS fallback
    ``iMessage;+;chat-guid``             Group conversation

Example config.toml::

    [channels.imessage]
    enabled       = true
    server_url    = "http://192.168.1.100:1234"
    password      = "ENV:BLUEBUBBLES_PASSWORD"
    poll_interval = 3.0
    method        = "apple-script"
    bot_handle    = "user@icloud.com"
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_DEFAULT_SERVER = "http://localhost:1234"
_API_VERSION = "v1"


class iMessageAdapter(ChannelAdapter):
    """iMessage adapter via BlueBubbles server REST API."""

    channel_id = "imessage"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._server_url: str = config.get("server_url", _DEFAULT_SERVER).rstrip("/")
        self._password: str = config.get("password", "")
        self._poll_interval: float = float(config.get("poll_interval", 5.0))
        self._method: str = config.get("method", "apple-script")
        self._bot_handle: str = config.get("bot_handle", "")
        self._poll_task: asyncio.Task[None] | None = None
        # epoch-ms high-water mark — only messages newer than this are processed
        self._after_ms: int = 0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the REST polling loop.

        Sets the high-water mark to *now* so only messages that arrive
        after ``connect()`` is called are dispatched.
        """
        self._after_ms = int(time.time() * 1000)
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(
            "imessage.connected server=%s poll_interval=%.1fs",
            self._server_url,
            self._poll_interval,
        )

    async def disconnect(self) -> None:
        """Cancel the polling loop and clean up."""
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        logger.info("imessage.disconnected")

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
        """Send a message via the BlueBubbles REST API.

        *target* must be a BlueBubbles chat GUID, e.g.:
        - ``iMessage;-;+15551234567``
        - ``iMessage;-;user@example.com``
        - ``iMessage;+;<group-chat-guid>``

        Returns the sent message GUID on success, ``None`` on error.
        """
        try:
            import httpx

            url = f"{self._server_url}/api/{_API_VERSION}/message/text"
            payload: dict[str, Any] = {
                "chatGuid": target,
                "message": text,
                "method": self._method,
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    json=payload,
                    params={"password": self._password},
                    timeout=15.0,
                )
                resp.raise_for_status()
                data = resp.json()
                msg_data = data.get("data") or {}
                return msg_data.get("guid")
        except Exception as exc:
            logger.error("imessage.send_error target=%s: %s", target, exc)
            return None

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the BlueBubbles server responds to a ping."""
        try:
            import httpx

            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._server_url}/api/{_API_VERSION}/ping",
                    params={"password": self._password},
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Polling loop
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        """Repeatedly call :meth:`_poll_once` at :attr:`_poll_interval` seconds."""
        while True:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("imessage.poll_loop_error: %s", exc)

    async def _poll_once(self) -> None:
        """Fetch recent messages from BlueBubbles and dispatch new ones."""
        try:
            import httpx

            url = f"{self._server_url}/api/{_API_VERSION}/message"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    params={
                        "password": self._password,
                        "limit": 50,
                        "after": self._after_ms,
                        "sort": "date",
                    },
                    timeout=10.0,
                )
                resp.raise_for_status()
                body = resp.json()
                messages: list[dict[str, Any]] = body.get("data") or []
                for msg_data in messages:
                    await self._process_message(msg_data)
                    date_ms = msg_data.get("dateCreated") or 0
                    if date_ms > self._after_ms:
                        self._after_ms = date_ms
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("imessage.poll_once_error: %s", exc)

    # ------------------------------------------------------------------
    # Message processing
    # ------------------------------------------------------------------

    async def _process_message(self, msg_data: dict[str, Any]) -> None:
        """Parse a BlueBubbles message dict and dispatch an :class:`InboundMessage`.

        Silently drops:
        - Outbound messages (``isFromMe=True``)
        - Messages with empty text
        - Messages from :attr:`_bot_handle` (echo-loop prevention)
        """
        if msg_data.get("isFromMe"):
            return

        text = (msg_data.get("text") or "").strip()
        if not text:
            return

        handle: dict[str, Any] = msg_data.get("handle") or {}
        sender_id: str = handle.get("address") or "unknown"
        sender_name: str = handle.get("displayName") or sender_id

        if self._bot_handle and sender_id == self._bot_handle:
            return

        chats: list[dict[str, Any]] = msg_data.get("chats") or []
        chat_guid: str = chats[0].get("guid", "") if chats else ""

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_name,
            text=text,
            thread_id=chat_guid or sender_id,
            timestamp=time.time(),
            raw=msg_data,
        )
        asyncio.create_task(self._dispatch(msg))

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["password"],
            "properties": {
                "server_url": {
                    "type": "string",
                    "default": _DEFAULT_SERVER,
                    "description": "Base URL of the BlueBubbles server",
                },
                "password": {
                    "type": "string",
                    "description": "BlueBubbles server password",
                },
                "poll_interval": {
                    "type": "number",
                    "default": 5.0,
                    "description": "Seconds between inbound-message polls",
                },
                "method": {
                    "type": "string",
                    "enum": ["apple-script", "private-api"],
                    "default": "apple-script",
                    "description": "Send method; 'private-api' requires the Private API helper",
                },
                "bot_handle": {
                    "type": "string",
                    "description": "Your Apple ID / phone number to prevent echo loops",
                },
            },
        }
