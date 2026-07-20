"""Matrix channel adapter using matrix-nio (async).

Supports:
- Receiving messages from rooms the bot is joined to
- Sending text and formatted (HTML) messages
- Auto-joining rooms on invite
- Commands: !reset, !memory, !status, !compact

Setup:
    pip install matrix-nio>=0.24.0

    Required config:
        channels.matrix.homeserver  = "https://matrix.org"
        channels.matrix.user_id     = "@mybot:matrix.org"
        channels.matrix.access_token = "ENV:MATRIX_ACCESS_TOKEN"
        channels.matrix.device_name = "NeuralCleave"        # optional

Usage::

    adapter = MatrixAdapter({
        "homeserver": "https://matrix.org",
        "user_id": "@mybot:matrix.org",
        "access_token": "syt_...",
    })
    adapter.on_message(my_handler)
    await adapter.connect()
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from neuralcleave.channels.base import ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_COMMANDS = {"!reset", "!memory", "!status", "!compact", "!voice", "!model"}


class MatrixAdapter(ChannelAdapter):
    """Matrix chat adapter using matrix-nio in async mode.

    Connects to any Matrix homeserver. Handles room invites automatically
    and dispatches all room text events to the registered handler.
    """

    channel_id = "matrix"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._homeserver = str(config.get("homeserver", "https://matrix.org"))
        self._user_id = str(config.get("user_id", ""))
        self._access_token = self._resolve(config.get("access_token", ""))
        self._device_name = str(config.get("device_name", "NeuralCleave"))
        self._client: Any | None = None
        self._sync_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from nio import (  # type: ignore[import]
                AsyncClient,
                InviteEvent,
                RoomMessageText,
            )
        except ImportError:
            raise RuntimeError("pip install matrix-nio>=0.24.0")

        self._client = AsyncClient(self._homeserver, self._user_id)
        self._client.access_token = self._access_token

        # Register event callbacks
        self._client.add_event_callback(self._on_message, RoomMessageText)
        self._client.add_event_callback(self._on_invite, InviteEvent)

        # Start background sync loop
        self._sync_task = asyncio.create_task(self._sync_loop())
        logger.info(
            "matrix.connected homeserver=%s user=%s",
            self._homeserver,
            self._user_id,
        )

    async def disconnect(self) -> None:
        if self._sync_task:
            self._sync_task.cancel()
            try:
                await self._sync_task
            except asyncio.CancelledError:
                pass
            self._sync_task = None

        if self._client:
            await self._client.close()
            self._client = None

        logger.info("matrix.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Send a text message to *target* (Matrix room ID, e.g. !abc:matrix.org)."""
        if not self._client:
            return None
        try:
            response = await self._client.room_send(
                room_id=target,
                message_type="m.room.message",
                content={"msgtype": "m.text", "body": text},
            )
            event_id = getattr(response, "event_id", None)
            logger.debug("matrix.sent room=%s event_id=%s", target, event_id)
            return event_id
        except Exception as exc:
            logger.error("matrix.send failed room=%s: %s", target, exc)
            return None

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["homeserver", "user_id", "access_token"],
            "properties": {
                "homeserver": {"type": "string", "description": "Matrix homeserver URL."},
                "user_id": {"type": "string", "description": "Full Matrix user ID (@bot:homeserver)."},
                "access_token": {"type": "string", "description": "Matrix access token (ENV:MATRIX_ACCESS_TOKEN)."},
                "device_name": {"type": "string", "default": "NeuralCleave"},
            },
        }

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_message(self, room: Any, event: Any) -> None:
        # Skip own messages
        if event.sender == self._user_id:
            return

        text = event.body.strip()

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=event.sender,
            sender_name=event.sender,
            text=text,
            thread_id=room.room_id,
            raw={"room_id": room.room_id, "event_id": event.event_id},
        )

        if self._handler:
            asyncio.create_task(self._handler(msg))

        logger.debug(
            "matrix.message room=%s sender=%s len=%d",
            room.room_id,
            event.sender,
            len(text),
        )

    async def _on_invite(self, room: Any, event: Any) -> None:
        """Auto-join rooms on invite."""
        if not self._client:
            return
        try:
            await self._client.join(room.room_id)
            logger.info("matrix.joined room=%s", room.room_id)
        except Exception as exc:
            logger.warning("matrix.join failed room=%s: %s", room.room_id, exc)

    async def _sync_loop(self) -> None:
        """Run Matrix sync indefinitely."""
        if not self._client:
            return
        try:
            await self._client.sync_forever(timeout=30000, full_state=True)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("matrix.sync_loop error: %s", exc)

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
