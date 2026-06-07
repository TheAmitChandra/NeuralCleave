"""Slack channel adapter using the slack-sdk Events API.

Supports:
- App mentions in channels (@YourBot ...)
- Direct messages to the bot
- Slash commands (/reset, /memory, /model, /status)
- File attachments (images, documents)

Setup:
    pip install slack-bolt>=1.18.0

    Required config:
        channels.slack.bot_token   = "ENV:SLACK_BOT_TOKEN"    # xoxb-...
        channels.slack.app_token   = "ENV:SLACK_APP_TOKEN"    # xapp-...  (for socket mode)
        channels.slack.signing_secret = "ENV:SLACK_SIGNING_SECRET"
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from cortexflow.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_COMMANDS = {"/reset", "/memory", "/model", "/status", "/compact", "/voice"}


class SlackAdapter(ChannelAdapter):
    """Slack adapter using slack-bolt in socket mode (no public URL needed).

    Socket mode uses ``SLACK_APP_TOKEN`` (xapp-...) to open a WebSocket to
    Slack's servers, so the bot works behind NAT/firewalls without ngrok.
    """

    channel_id = "slack"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._bot_token = self._resolve(config.get("bot_token", ""))
        self._app_token = self._resolve(config.get("app_token", ""))
        self._signing_secret = self._resolve(config.get("signing_secret", ""))
        self._bot_user_id: str | None = None
        self._app: Any | None = None
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        try:
            from slack_bolt.async_app import AsyncApp  # type: ignore[import]
            from slack_bolt.adapter.socket_mode.async_handler import (  # type: ignore[import]
                AsyncSocketModeHandler,
            )
        except ImportError:
            raise RuntimeError("pip install slack-bolt")

        if not self._bot_token:
            raise RuntimeError("Slack bot_token not configured")
        if not self._app_token:
            raise RuntimeError("Slack app_token (xapp-...) not configured")

        self._app = AsyncApp(
            token=self._bot_token,
            signing_secret=self._signing_secret or None,
        )

        # Resolve our own bot user ID so we can filter self-messages
        client = self._app.client
        auth = await client.auth_test()
        self._bot_user_id = auth.get("user_id")
        logger.info("SlackAdapter connected as user_id=%s", self._bot_user_id)

        self._register_handlers()

        handler = AsyncSocketModeHandler(self._app, self._app_token)
        self._task = asyncio.create_task(handler.start_async())
        logger.info("SlackAdapter socket mode started")

    async def disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("SlackAdapter disconnected")

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
        if not self._app:
            raise RuntimeError("SlackAdapter not connected")

        kwargs: dict[str, Any] = {"channel": target, "text": text}
        if reply_to:
            kwargs["thread_ts"] = reply_to

        resp = await self._app.client.chat_postMessage(**kwargs)
        return resp.get("ts")  # Slack message timestamp as ID

    # ------------------------------------------------------------------
    # Handler registration
    # ------------------------------------------------------------------

    def _register_handlers(self) -> None:
        app = self._app

        @app.event("app_mention")
        async def on_mention(event: dict, say: Any) -> None:
            await self._on_event(event)

        @app.event("message")
        async def on_message(event: dict) -> None:
            # Only handle DMs; skip bot messages and channel noise
            if event.get("channel_type") == "im" and not event.get("bot_id"):
                await self._on_event(event)

        for cmd in _COMMANDS:
            # Slack slash commands must be registered per-command in the app
            @app.command(cmd)
            async def on_slash(ack: Any, command: dict) -> None:
                await ack()
                await self._on_command(command)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _on_event(self, event: dict) -> None:
        user_id = event.get("user", "")
        if user_id == self._bot_user_id:
            return  # ignore own messages

        text = event.get("text", "") or ""
        # Strip bot mention prefix (<@UXXXXXXX> ...)
        if self._bot_user_id and text.startswith(f"<@{self._bot_user_id}>"):
            text = text[len(f"<@{self._bot_user_id}>"):].strip()

        attachments = [
            Attachment(
                type=_guess_type(f.get("mimetype", "")),
                url=f.get("url_private"),
                filename=f.get("name"),
                mime_type=f.get("mimetype"),
            )
            for f in event.get("files", [])
        ]

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=user_id,
            sender_name=event.get("username") or user_id,
            text=text or None,
            attachments=attachments,
            thread_id=event.get("thread_ts"),
            reply_to_id=event.get("thread_ts"),
            raw=event,
        )
        await self._dispatch(msg)

    async def _on_command(self, command: dict) -> None:
        text = f"{command.get('command', '')} {command.get('text', '')}".strip()
        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=command.get("user_id", ""),
            sender_name=command.get("user_name", ""),
            text=text,
            raw=command,
        )
        await self._dispatch(msg)

    @staticmethod
    def _resolve(value: str) -> str:
        import os
        if isinstance(value, str) and value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "bot_token": {"type": "string", "description": "xoxb-... Slack bot token"},
                "app_token": {"type": "string", "description": "xapp-... for socket mode"},
                "signing_secret": {"type": "string", "description": "Slack app signing secret"},
            },
            "required": ["bot_token", "app_token"],
        }


def _guess_type(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    return "document"
