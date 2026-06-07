"""Mastodon channel adapter using Mastodon.py.

Supports:
- Receiving mentions via user streaming
- Receiving direct messages (DMs)
- Sending replies as public, unlisted, or direct posts
- Mastodon bot commands: @bot !reset, @bot !memory, etc.

Setup:
    pip install Mastodon.py>=1.8.0

    Steps:
        1. Create a Mastodon app: mastodon.social → Settings → Development
        2. Or use Mastodon.create_app() — see below

    Required config:
        channels.mastodon.instance_url  = "https://mastodon.social"
        channels.mastodon.access_token  = "ENV:MASTODON_ACCESS_TOKEN"
        channels.mastodon.bot_username  = "@cortexflow"  # your bot's username

Usage::

    adapter = MastodonAdapter({
        "instance_url": "https://mastodon.social",
        "access_token": "your-access-token",
        "bot_username": "@mybot",
    })
    adapter.on_message(my_handler)
    await adapter.connect()
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from cortexflow.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

# Strip HTML tags from toot content
_HTML_TAG = re.compile(r"<[^>]+>")


def _strip_html(html: str) -> str:
    return _HTML_TAG.sub("", html).strip()


class MastodonAdapter(ChannelAdapter):
    """Mastodon adapter — receives mentions via streaming, sends toots as replies.

    Uses Mastodon.py's streaming listener in a background asyncio task.
    Mastodon.py's streaming is synchronous, so it runs in a thread executor.
    """

    channel_id = "mastodon"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._instance_url = str(config.get("instance_url", "https://mastodon.social"))
        self._access_token = self._resolve(config.get("access_token", ""))
        self._bot_username = str(config.get("bot_username", ""))
        self._visibility = str(config.get("reply_visibility", "unlisted"))
        self._client: Any | None = None
        self._stream_task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from mastodon import Mastodon  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install Mastodon.py>=1.8.0")

        self._client = Mastodon(
            access_token=self._access_token,
            api_base_url=self._instance_url,
        )

        self._stream_task = asyncio.create_task(self._stream_mentions())
        logger.info(
            "mastodon.connected instance=%s bot=%s",
            self._instance_url,
            self._bot_username,
        )

    async def disconnect(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
        self._client = None
        logger.info("mastodon.disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list | None = None,
    ) -> str | None:
        """Post a toot. *target* is the account to mention (e.g. '@user@instance').

        Args:
            target:   Account handle to @-mention in the reply.
            text:     Message body (may be truncated to 500 chars).
            reply_to: Status ID of the toot to reply to.
        """
        if not self._client:
            return None

        content = f"{target} {text}" if target else text
        # Mastodon limit is typically 500 chars
        content = content[:500]

        try:
            loop = asyncio.get_running_loop()
            status = await loop.run_in_executor(
                None,
                lambda: self._client.status_post(
                    content,
                    in_reply_to_id=reply_to,
                    visibility=self._visibility,
                ),
            )
            status_id = str(status.get("id", ""))
            logger.debug("mastodon.sent status_id=%s len=%d", status_id, len(content))
            return status_id
        except Exception as exc:
            logger.error("mastodon.send failed target=%s: %s", target, exc)
            return None

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["instance_url", "access_token"],
            "properties": {
                "instance_url": {"type": "string", "description": "Mastodon instance URL (e.g. https://mastodon.social)."},
                "access_token": {"type": "string", "description": "OAuth2 access token (ENV:MASTODON_ACCESS_TOKEN)."},
                "bot_username": {"type": "string", "description": "@username of this bot (used to strip self-mentions)."},
                "reply_visibility": {"type": "string", "enum": ["public", "unlisted", "private", "direct"], "default": "unlisted"},
            },
        }

    # ------------------------------------------------------------------
    # Streaming
    # ------------------------------------------------------------------

    async def _stream_mentions(self) -> None:
        """Stream user notifications in a thread executor (Mastodon.py is sync)."""
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(None, self._blocking_stream)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("mastodon.stream error: %s", exc)

    def _blocking_stream(self) -> None:
        """Blocking stream listener — runs in thread executor."""
        try:
            from mastodon import StreamListener  # type: ignore[import]
        except ImportError:
            return

        adapter_ref = self

        class _Listener(StreamListener):
            def on_notification(self, notification: dict) -> None:
                if notification.get("type") != "mention":
                    return
                status = notification.get("status", {})
                account = status.get("account", {})
                content_html = status.get("content", "")
                text = _strip_html(content_html)

                # Strip bot's own @-mention from the message
                if adapter_ref._bot_username:
                    text = text.replace(adapter_ref._bot_username, "").strip()

                sender_id = account.get("acct", "unknown")
                status_id = str(status.get("id", ""))

                if not text:
                    return

                # Build attachments from media
                attachments: list[Attachment] = []
                for media in status.get("media_attachments", []):
                    attachments.append(
                        Attachment(
                            type=media.get("type", "document"),
                            url=media.get("url"),
                        )
                    )

                msg = InboundMessage(
                    channel=adapter_ref.channel_id,
                    sender_id=sender_id,
                    sender_name=account.get("display_name", sender_id),
                    text=text,
                    attachments=attachments,
                    thread_id=status_id,  # use status ID as thread context
                    raw=status,
                )

                if adapter_ref._handler:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(adapter_ref._handler(msg))
                    loop.close()

                logger.debug(
                    "mastodon.mention from=%s status=%s len=%d",
                    sender_id,
                    status_id,
                    len(text),
                )

        if self._client:
            self._client.stream_user(_Listener())

    @staticmethod
    def _resolve(value: str) -> str:
        if isinstance(value, str) and value.startswith("ENV:"):
            import os
            return os.getenv(value[4:], "")
        return value or ""
