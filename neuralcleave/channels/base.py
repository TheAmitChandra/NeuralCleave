"""Channel adapter abstract base class and shared data types."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class Attachment:
    """A file or media attachment from a channel message."""

    type: str  # "image" | "audio" | "video" | "document"
    url: str | None = None
    data: bytes | None = None
    filename: str | None = None
    mime_type: str | None = None


@dataclass
class InboundMessage:
    """Normalised inbound message from any channel adapter."""

    channel: str
    sender_id: str
    sender_name: str
    text: str | None
    attachments: list[Attachment] = field(default_factory=list)
    thread_id: str | None = None
    reply_to_id: str | None = None
    timestamp: float = field(default_factory=time.time)
    raw: dict[str, Any] = field(default_factory=dict)


#: A coroutine function that handles an inbound message.
MessageHandler = Callable[[InboundMessage], Awaitable[None]]


class ChannelAdapter(ABC):
    """Abstract base for all platform channel adapters.

    Subclasses must set ``channel_id`` as a class attribute and implement
    ``connect``, ``disconnect``, and ``send``.
    """

    channel_id: str  # e.g. "telegram" | "discord" | "slack"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self._handler: MessageHandler | None = None

    @abstractmethod
    async def connect(self) -> None:
        """Establish connection to the platform. Raises on failure."""
        ...

    @abstractmethod
    async def disconnect(self) -> None:
        """Gracefully disconnect from the platform."""
        ...

    @abstractmethod
    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        """Send a message to *target* (platform-specific ID).

        Returns the sent message ID if the platform provides one.
        """
        ...

    @property
    def is_connected(self) -> bool:
        """True when the adapter has an active connection or background task.

        Checks each attribute name used across all built-in adapters so the
        channel list endpoint never needs updating when a new adapter is added.
        Subclasses can override this for custom connection models.
        """
        return (
            getattr(self, "_task", None) is not None         # Discord, Email, Slack
            or getattr(self, "_ws_task", None) is not None   # Mattermost
            or getattr(self, "_sync_task", None) is not None # Matrix
            or getattr(self, "_read_task", None) is not None # Signal
            or getattr(self, "_runner", None) is not None    # SMS, Teams, Webhook
            or getattr(self, "_poll_task", None) is not None # Nextcloud
            or getattr(self, "_process", None) is not None   # Signal subprocess
            or getattr(self, "_app", None) is not None       # Telegram, Slack (cleared on disconnect)
            or getattr(self, "_client", None) is not None    # Matrix, Mastodon, Discord
            or bool(getattr(self, "_connected", False))      # IRC, WhatsApp
        )

    def on_message(self, handler: MessageHandler) -> None:
        """Register the handler that receives all inbound messages."""
        self._handler = handler

    async def _dispatch(self, message: InboundMessage) -> None:
        """Forward *message* to the registered handler (if any)."""
        if self._handler is not None:
            await self._handler(message)

    def get_config_schema(self) -> dict[str, Any]:
        """Return a JSON Schema describing this adapter's config options."""
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
            },
            "required": [],
        }

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(channel_id={self.channel_id!r})"
