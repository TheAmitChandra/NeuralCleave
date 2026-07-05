"""Discord channel adapter using discord.py v2."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class DiscordAdapter(ChannelAdapter):
    """Discord Bot adapter.

    Requires ``discord.py>=2.0`` (``pip install discord.py``).

    Config keys:
        bot_token (str): Discord bot token. Use ``ENV:DISCORD_BOT_TOKEN``.
        prefix (str): Command prefix for text commands. Default: ``!``.
    """

    channel_id = "discord"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._client: Any | None = None
        self._task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        try:
            import discord
        except ImportError:
            raise RuntimeError(
                "Discord adapter requires: pip install 'discord.py>=2.0'"
            )

        token = self._resolve(self.config.get("bot_token", ""))
        if not token:
            raise ValueError("channels.discord.bot_token is required (or set DISCORD_BOT_TOKEN)")

        intents = discord.Intents.default()
        intents.message_content = True
        intents.dm_messages = True

        class _BotClient(discord.Client):
            def __init__(self_inner, adapter: DiscordAdapter, **kwargs: Any) -> None:
                super().__init__(**kwargs)
                self_inner._adapter = adapter

            async def on_ready(self_inner) -> None:
                logger.info("Discord adapter logged in as %s", self_inner.user)

            async def on_message(self_inner, message: discord.Message) -> None:
                if message.author == self_inner.user:
                    return
                attachments = [
                    Attachment(
                        type=_guess_type(a.content_type or ""),
                        url=a.url,
                        filename=a.filename,
                        mime_type=a.content_type,
                    )
                    for a in message.attachments
                ]
                inbound = InboundMessage(
                    channel=self_inner._adapter.channel_id,
                    sender_id=str(message.author.id),
                    sender_name=str(message.author.display_name),
                    text=message.content or None,
                    attachments=attachments,
                    thread_id=str(message.channel.id),
                    reply_to_id=(
                        str(message.reference.message_id)
                        if message.reference
                        else None
                    ),
                    raw={"guild_id": str(message.guild.id) if message.guild else None},
                )
                await self_inner._adapter._dispatch(inbound)

        self._client = _BotClient(adapter=self, intents=intents)
        self._task = asyncio.create_task(self._client.start(token))
        logger.info("Discord adapter connecting...")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
        if self._task is not None:
            self._task.cancel()
            self._task = None
        logger.info("Discord adapter disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        if self._client is None:
            logger.error("discord.send called before connect()")
            return None
        try:
            channel = self._client.get_channel(int(target))
            if channel is None:
                channel = await self._client.fetch_channel(int(target))
            msg = await channel.send(content=text)
            return str(msg.id)
        except Exception as exc:
            logger.error("Discord send failed target=%s: %s", target, exc)
            return None

    @staticmethod
    def _resolve(value: str) -> str:
        if value.startswith("ENV:"):
            return os.getenv(value[4:], "")
        return value

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean", "default": False},
                "bot_token": {
                    "type": "string",
                    "description": "Bot token from Discord Developer Portal. Use ENV:DISCORD_BOT_TOKEN.",
                },
                "prefix": {"type": "string", "default": "!"},
            },
            "required": ["bot_token"],
        }


def _guess_type(content_type: str) -> str:
    if content_type.startswith("image/"):
        return "image"
    if content_type.startswith("audio/"):
        return "audio"
    if content_type.startswith("video/"):
        return "video"
    return "document"
