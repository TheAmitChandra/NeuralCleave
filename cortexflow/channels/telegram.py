"""Telegram channel adapter using python-telegram-bot v21 (async)."""

from __future__ import annotations

import logging
import os
from typing import Any

from cortexflow.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class TelegramAdapter(ChannelAdapter):
    """Telegram Bot API adapter.

    Requires ``python-telegram-bot>=21.0`` (``pip install python-telegram-bot``).

    Config keys:
        bot_token (str): Telegram bot token. Use ``ENV:TELEGRAM_BOT_TOKEN``.
    """

    channel_id = "telegram"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._app: Any | None = None

    async def connect(self) -> None:
        try:
            from telegram.ext import ApplicationBuilder, filters
            from telegram.ext import MessageHandler as TGHandler
        except ImportError:
            raise RuntimeError(
                "Telegram adapter requires: pip install 'python-telegram-bot>=21.0'"
            )

        token = self._resolve(self.config.get("bot_token", ""))
        if not token:
            raise ValueError("channels.telegram.bot_token is required (or set TELEGRAM_BOT_TOKEN)")

        self._app = ApplicationBuilder().token(token).build()
        self._app.add_handler(
            TGHandler(
                filters.TEXT | filters.VOICE | filters.PHOTO | filters.Document.ALL,
                self._on_update,
            )
        )
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram adapter connected")

    async def disconnect(self) -> None:
        if self._app is not None:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
            self._app = None
            logger.info("Telegram adapter disconnected")

    async def send(
        self,
        target: str,
        text: str,
        *,
        reply_to: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> str | None:
        if self._app is None:
            raise RuntimeError("TelegramAdapter.connect() has not been called")
        try:
            kwargs: dict[str, Any] = {
                "chat_id": target,
                "text": text,
                "parse_mode": "Markdown",
            }
            if reply_to:
                kwargs["reply_to_message_id"] = int(reply_to)
            msg = await self._app.bot.send_message(**kwargs)
            return str(msg.message_id)
        except Exception as exc:
            logger.error("Telegram send failed target=%s: %s", target, exc)
            return None

    async def _on_update(self, update: Any, context: Any) -> None:
        if update.message is None:
            return
        msg = update.message
        text: str | None = msg.text or msg.caption
        attachments: list[Attachment] = []

        if msg.voice:
            attachments.append(
                Attachment(type="audio", filename="voice.ogg", mime_type="audio/ogg")
            )
        if msg.photo:
            file = await context.bot.get_file(msg.photo[-1].file_id)
            attachments.append(
                Attachment(type="image", url=file.file_path, mime_type="image/jpeg")
            )
        if msg.document:
            attachments.append(
                Attachment(
                    type="document",
                    filename=msg.document.file_name,
                    mime_type=msg.document.mime_type,
                )
            )

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=str(msg.from_user.id) if msg.from_user else "unknown",
            sender_name=msg.from_user.full_name if msg.from_user else "Unknown",
            text=text,
            attachments=attachments,
            thread_id=str(msg.chat_id),
            reply_to_id=(
                str(msg.reply_to_message.message_id) if msg.reply_to_message else None
            ),
            raw={"update_id": update.update_id, "message_id": msg.message_id},
        )
        await self._dispatch(inbound)

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
                    "description": "Bot token from @BotFather. Use ENV:TELEGRAM_BOT_TOKEN.",
                },
            },
            "required": ["bot_token"],
        }
