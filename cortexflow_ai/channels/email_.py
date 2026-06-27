"""Email channel adapter — IMAP polling (inbound) + SMTP send (outbound).

Works with Gmail, Outlook, Fastmail, or any IMAP/SMTP provider.

Setup (Gmail example):
    Enable "App Passwords" (requires 2FA):
    https://myaccount.google.com/apppasswords

    Required config:
        channels.email.imap_host = "imap.gmail.com"
        channels.email.smtp_host = "smtp.gmail.com"
        channels.email.username  = "ENV:EMAIL_USER"
        channels.email.password  = "ENV:EMAIL_PASSWORD"

Optional config:
    poll_interval  = 60      # seconds between IMAP checks (default 60)
    imap_port      = 993     # default SSL port
    smtp_port      = 587     # default STARTTLS port
    mailbox        = "INBOX" # folder to watch

Requires:
    pip install aiosmtplib aioimaplib
"""

from __future__ import annotations

import asyncio
import email
import email.policy
import logging
import os
from email.message import EmailMessage
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)


class EmailAdapter(ChannelAdapter):
    """IMAP+SMTP email channel adapter.

    Polls IMAP on a configurable interval and dispatches new messages.
    Sends replies via SMTP with proper threading headers (In-Reply-To).
    """

    channel_id = "email"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._imap_host: str = config.get("imap_host", "imap.gmail.com")
        self._imap_port: int = int(config.get("imap_port", 993))
        self._smtp_host: str = config.get("smtp_host", "smtp.gmail.com")
        self._smtp_port: int = int(config.get("smtp_port", 587))
        self._username: str = self._resolve(config.get("username", ""))
        self._password: str = self._resolve(config.get("password", ""))
        self._mailbox: str = config.get("mailbox", "INBOX")
        self._poll_interval: int = int(config.get("poll_interval", 60))
        self._task: asyncio.Task | None = None  # type: ignore[type-arg]
        self._seen_uids: set[str] = set()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        if not self._username or not self._password:
            raise RuntimeError("Email username/password not configured")
        # Quick connectivity check
        await self._imap_check()
        logger.info(
            "EmailAdapter connected user=%s host=%s poll_interval=%ds",
            self._username, self._imap_host, self._poll_interval,
        )
        self._task = asyncio.create_task(self._poll_loop())

    async def disconnect(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("EmailAdapter disconnected")

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
        try:
            import aiosmtplib  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aiosmtplib")

        msg = EmailMessage()
        msg["From"] = self._username
        msg["To"] = target
        msg["Subject"] = "Re: CortexFlow" if reply_to else "CortexFlow"
        msg.set_content(text)

        if reply_to:
            msg["In-Reply-To"] = reply_to
            msg["References"] = reply_to

        await aiosmtplib.send(
            msg,
            hostname=self._smtp_host,
            port=self._smtp_port,
            username=self._username,
            password=self._password,
            start_tls=True,
        )
        logger.debug("EmailAdapter sent to=%s", target)
        return None  # SMTP doesn't return a message ID easily

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._imap_check()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("EmailAdapter poll error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _imap_check(self) -> None:
        try:
            import aioimaplib  # type: ignore[import]
        except ImportError:
            raise RuntimeError("pip install aioimaplib")

        client = aioimaplib.IMAP4_SSL(host=self._imap_host, port=self._imap_port)
        await client.wait_hello_from_server()
        await client.login(self._username, self._password)
        await client.select(self._mailbox)

        # Fetch unseen messages
        _, data = await client.search("UNSEEN")
        if not data or not data[0]:
            await client.logout()
            return

        uids = data[0].decode().split()
        new_uids = [u for u in uids if u not in self._seen_uids]

        for uid in new_uids:
            self._seen_uids.add(uid)
            try:
                _, msg_data = await client.fetch(uid, "(RFC822)")
                raw = msg_data[1]
                if isinstance(raw, bytes):
                    parsed = email.message_from_bytes(raw, policy=email.policy.default)
                    await self._dispatch_email(parsed)
            except Exception as exc:
                logger.warning("EmailAdapter fetch uid=%s error: %s", uid, exc)

        await client.logout()

    async def _dispatch_email(self, msg: Any) -> None:
        sender = str(msg.get("From", ""))
        sender_id = _extract_address(sender)
        subject = str(msg.get("Subject", ""))
        message_id = str(msg.get("Message-ID", ""))
        in_reply_to = str(msg.get("In-Reply-To", "")) or None

        # Extract plain text body
        body: str | None = None
        attachments: list[Attachment] = []

        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                if ct == "text/plain" and body is None:
                    body = part.get_content()
                elif ct not in ("text/plain", "text/html", "multipart/mixed", "multipart/alternative"):
                    filename = part.get_filename()
                    data = part.get_payload(decode=True)
                    if data:
                        attachments.append(
                            Attachment(
                                type=_mime_to_type(ct),
                                data=data,
                                filename=filename,
                                mime_type=ct,
                            )
                        )
        else:
            body = msg.get_content()

        if body:
            body = body.strip()

        inbound = InboundMessage(
            channel=self.channel_id,
            sender_id=sender_id,
            sender_name=sender_id,
            text=f"Subject: {subject}\n\n{body}" if subject and body else (body or subject or None),
            attachments=attachments,
            thread_id=in_reply_to or message_id,
            reply_to_id=in_reply_to,
            raw={"from": sender, "subject": subject, "message_id": message_id},
        )
        await self._dispatch(inbound)

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
                "imap_host": {"type": "string", "default": "imap.gmail.com"},
                "smtp_host": {"type": "string", "default": "smtp.gmail.com"},
                "imap_port": {"type": "integer", "default": 993},
                "smtp_port": {"type": "integer", "default": 587},
                "username": {"type": "string"},
                "password": {"type": "string"},
                "mailbox": {"type": "string", "default": "INBOX"},
                "poll_interval": {"type": "integer", "default": 60},
            },
            "required": ["username", "password"],
        }


def _extract_address(header: str) -> str:
    """Extract raw email address from 'Name <addr>' format."""
    if "<" in header and ">" in header:
        return header.split("<")[1].split(">")[0].strip()
    return header.strip()


def _mime_to_type(mime: str) -> str:
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("audio/"):
        return "audio"
    if mime.startswith("video/"):
        return "video"
    return "document"
