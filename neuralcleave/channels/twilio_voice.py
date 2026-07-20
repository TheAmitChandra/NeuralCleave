"""Twilio Voice channel adapter — multi-turn speech conversations.

CortexFlow answers inbound phone calls via Twilio Voice.  The adapter
runs a lightweight ``aiohttp`` webhook server that:

1. Answers calls with a greeting and a ``<Gather input="speech">`` TwiML
   verb so Twilio transcribes the caller's speech server-side.
2. On each transcription webhook, dispatches an ``InboundMessage`` with the
   transcribed text and waits (up to ``response_timeout`` seconds) for the
   AI handler to call ``send()`` with a spoken reply.
3. Returns the reply wrapped in ``<Say>`` TwiML, followed by a new
   ``<Gather>`` for the next turn — enabling multi-turn voice conversations.

This adapter uses an ``asyncio.Future`` per active call (keyed by
``CallSid``) to bridge the synchronous Twilio request-response cycle with
CortexFlow's async message-handler pipeline.

Authentication:
    ``account_sid``  Twilio account SID — used for REST API calls (``send()``
                     fallback and ``ping()``).
    ``auth_token``   Twilio auth token — used for ``X-Twilio-Signature``
                     webhook verification and REST API HTTP Basic Auth.

Config keys:
    account_sid      Twilio account SID (required for send/ping)
    auth_token       Twilio auth token (required for sig verification)
    host             Webhook server bind host (default: ``"0.0.0.0"``)
    port             Webhook server port (default: 8088)
    incoming_path    Path for incoming call webhook (default:
                     ``"/webhook/twilio_voice/call"``)
    transcript_path  Path for transcription webhook (default:
                     ``"/webhook/twilio_voice/transcript"``)
    greeting         Opening words spoken to the caller (default:
                     ``"Hello! How can I help you?"``)
    voice            Twilio TTS voice name (default: ``"alice"``); supports
                     Amazon Polly voices such as ``"Polly.Joanna"``
    language         BCP-47 language tag for STT + TTS (default: ``"en-US"``)
    response_timeout Seconds to wait for the AI handler to reply (default: 25.0)
    speech_timeout   Twilio ``speechTimeout`` value (default: ``"auto"``)

Outbound target format:
    The ``CallSid`` string received from Twilio (e.g. ``CA3f…``).  Pass it as
    the *target* argument to ``send()`` to respond to an active call.

Example config.toml::

    [channels.twilio_voice]
    enabled          = true
    account_sid      = "ENV:TWILIO_ACCOUNT_SID"
    auth_token       = "ENV:TWILIO_AUTH_TOKEN"
    port             = 8088
    greeting         = "Hello! I'm your AI assistant. How can I help?"
    voice            = "alice"
    language         = "en-US"
    response_timeout = 25.0
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import html
import logging
import time
from typing import Any

from cortexflow_ai.channels.base import Attachment, ChannelAdapter, InboundMessage

logger = logging.getLogger(__name__)

_TWILIO_BASE = "https://api.twilio.com/2010-04-01"
_TWIML_CONTENT_TYPE = "application/xml"
_TWIML_DECLARATION = '<?xml version="1.0" encoding="UTF-8"?>'


class TwilioVoiceAdapter(ChannelAdapter):
    """Twilio Voice adapter — multi-turn speech via TwiML + asyncio Futures."""

    channel_id = "twilio_voice"

    def __init__(self, config: dict[str, Any]) -> None:
        super().__init__(config)
        self._account_sid: str = config.get("account_sid", "")
        self._auth_token: str = config.get("auth_token", "")
        self._host: str = config.get("host", "0.0.0.0")
        self._port: int = int(config.get("port", 8088))
        self._incoming_path: str = config.get(
            "incoming_path", "/webhook/twilio_voice/call"
        )
        self._transcript_path: str = config.get(
            "transcript_path", "/webhook/twilio_voice/transcript"
        )
        self._greeting: str = config.get("greeting", "Hello! How can I help you?")
        self._voice: str = config.get("voice", "alice")
        self._language: str = config.get("language", "en-US")
        self._response_timeout: float = float(config.get("response_timeout", 25.0))
        self._speech_timeout: str = str(config.get("speech_timeout", "auto"))
        self._runner: Any = None
        # Per-call futures keyed by CallSid
        self._pending: dict[str, asyncio.Future[str]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def connect(self) -> None:
        """Start the aiohttp webhook server."""
        from aiohttp import web

        app = web.Application()
        app.router.add_post(self._incoming_path, self._handle_incoming)
        app.router.add_get(self._incoming_path, self._handle_health)
        app.router.add_post(self._transcript_path, self._handle_transcript)
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self._host, self._port)
        await site.start()
        logger.info(
            "twilio_voice.connected host=%s port=%d incoming=%s transcript=%s",
            self._host,
            self._port,
            self._incoming_path,
            self._transcript_path,
        )

    async def disconnect(self) -> None:
        """Stop the webhook server and cancel all pending call futures."""
        for future in list(self._pending.values()):
            if not future.done():
                future.cancel()
        self._pending.clear()

        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
        logger.info("twilio_voice.disconnected")

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
        """Deliver a spoken reply to an active voice call.

        *target* is the ``CallSid`` of the call to reply to.

        **Primary path** — request-response cycle: if the call has a pending
        :class:`asyncio.Future` (created when :meth:`_handle_transcript`
        received the caller's speech), resolve it with *text*.
        :meth:`_handle_transcript` is blocked awaiting that future and will
        immediately return TwiML ``<Say>`` + ``<Gather>`` with the reply.

        **Fallback path** — proactive send: if no pending future exists, use
        the Twilio REST API to update the live call's TwiML.

        Returns *target* (``CallSid``) on success, ``None`` on error.
        """
        if not target:
            logger.warning("twilio_voice.send: target (CallSid) is empty")
            return None

        future = self._pending.get(target)
        if future is not None and not future.done():
            future.set_result(text)
            return target

        return await self._update_call(target, text)

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    async def ping(self) -> bool:
        """Return True if the Twilio credentials are valid.

        Calls ``GET /Accounts/{account_sid}.json`` with HTTP Basic Auth.
        """
        if not self._account_sid or not self._auth_token:
            return False
        try:
            import httpx

            url = f"{_TWILIO_BASE}/Accounts/{self._account_sid}.json"
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    url,
                    auth=(self._account_sid, self._auth_token),
                    timeout=5.0,
                )
                return resp.status_code == 200
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Webhook signature verification
    # ------------------------------------------------------------------

    def _verify_signature(
        self,
        url: str,
        params: dict[str, str],
        signature: str,
    ) -> bool:
        """Verify a Twilio ``X-Twilio-Signature`` header.

        Algorithm: ``base64(HMAC-SHA1(auth_token, url + sorted_params))``
        where *sorted_params* is each POST key-value pair concatenated in
        ascending key order (no separator between pairs or key/value).

        Returns ``True`` (permissive) when no ``auth_token`` is configured.
        Returns ``False`` for an empty signature or digest mismatch.
        """
        if not self._auth_token:
            return True
        if not signature:
            return False
        try:
            s = url
            for key in sorted(params.keys()):
                s += key + params[key]
            mac = hmac.new(
                self._auth_token.encode("utf-8"),
                s.encode("utf-8"),
                hashlib.sha1,
            ).digest()
            expected = base64.b64encode(mac).decode()
            return hmac.compare_digest(expected, signature)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # TwiML helpers
    # ------------------------------------------------------------------

    def _twiml_gather(self, say_text: str = "") -> str:
        """Return TwiML that optionally speaks *say_text* then gathers speech."""
        say = (
            f'  <Say voice="{self._voice}" language="{self._language}">'
            f"{html.escape(say_text)}</Say>\n"
            if say_text
            else ""
        )
        return (
            f"{_TWIML_DECLARATION}\n"
            "<Response>\n"
            f"{say}"
            f'  <Gather input="speech" action="{self._transcript_path}"'
            f' method="POST" speechTimeout="{self._speech_timeout}"'
            f' language="{self._language}"/>\n'
            "  <Hangup/>\n"
            "</Response>"
        )

    def _twiml_say_and_gather(self, text: str) -> str:
        """Return TwiML that speaks *text* then gathers the next speech input."""
        return (
            f"{_TWIML_DECLARATION}\n"
            "<Response>\n"
            f'  <Say voice="{self._voice}" language="{self._language}">'
            f"{html.escape(text)}</Say>\n"
            f'  <Gather input="speech" action="{self._transcript_path}"'
            f' method="POST" speechTimeout="{self._speech_timeout}"'
            f' language="{self._language}"/>\n'
            "  <Hangup/>\n"
            "</Response>"
        )

    def _twiml_error(self, message: str = "Sorry, something went wrong. Goodbye.") -> str:
        """Return TwiML that speaks *message* and hangs up."""
        return (
            f"{_TWIML_DECLARATION}\n"
            "<Response>\n"
            f'  <Say voice="{self._voice}" language="{self._language}">'
            f"{html.escape(message)}</Say>\n"
            "  <Hangup/>\n"
            "</Response>"
        )

    # ------------------------------------------------------------------
    # Webhook handlers
    # ------------------------------------------------------------------

    async def _handle_incoming(self, request: Any) -> Any:
        """Handle an incoming Twilio Voice call — return greeting + Gather."""
        from aiohttp import web

        try:
            params: dict[str, str] = dict(await request.post())
        except Exception:
            params = {}

        if self._auth_token:
            sig = request.headers.get("X-Twilio-Signature", "")
            if not self._verify_signature(str(request.url), params, sig):
                logger.warning("twilio_voice.invalid_signature on incoming call")
                return web.Response(status=400, text="Bad signature")

        call_sid = params.get("CallSid", "unknown")
        caller = params.get("From", "unknown")
        logger.info(
            "twilio_voice.call_incoming CallSid=%s From=%s", call_sid, caller
        )

        twiml = self._twiml_gather(say_text=self._greeting)
        return web.Response(
            status=200,
            body=twiml.encode(),
            content_type=_TWIML_CONTENT_TYPE,
        )

    async def _handle_transcript(self, request: Any) -> Any:
        """Handle a Twilio speech transcription — dispatch and await AI reply.

        Creates an ``asyncio.Future`` for the ``CallSid``, dispatches an
        ``InboundMessage`` to the registered handler, then waits up to
        :attr:`_response_timeout` seconds for the handler to call
        :meth:`send`.  Returns ``<Say>`` + ``<Gather>`` TwiML on success or
        an error TwiML + ``<Hangup>`` on timeout.
        """
        from aiohttp import web

        try:
            params: dict[str, str] = dict(await request.post())
        except Exception:
            params = {}

        if self._auth_token:
            sig = request.headers.get("X-Twilio-Signature", "")
            if not self._verify_signature(str(request.url), params, sig):
                logger.warning("twilio_voice.invalid_signature on transcript")
                return web.Response(status=400, text="Bad signature")

        call_sid = params.get("CallSid", "unknown")
        speech = (params.get("SpeechResult") or "").strip()

        if not speech:
            twiml = self._twiml_gather(
                say_text="I didn't catch that. Could you repeat?"
            )
            return web.Response(
                status=200,
                body=twiml.encode(),
                content_type=_TWIML_CONTENT_TYPE,
            )

        caller = params.get("From", "unknown")
        future: asyncio.Future[str] = asyncio.Future()
        self._pending[call_sid] = future

        msg = InboundMessage(
            channel=self.channel_id,
            sender_id=caller,
            sender_name=caller,
            text=speech,
            thread_id=call_sid,
            timestamp=time.time(),
            raw=dict(params),
        )
        asyncio.create_task(self._dispatch(msg))

        try:
            reply = await asyncio.wait_for(future, timeout=self._response_timeout)
            twiml = self._twiml_say_and_gather(reply)
        except asyncio.TimeoutError:
            logger.warning(
                "twilio_voice.response_timeout CallSid=%s after %.1fs",
                call_sid,
                self._response_timeout,
            )
            twiml = self._twiml_error(
                "I'm sorry, I couldn't process that in time. Goodbye."
            )
        finally:
            self._pending.pop(call_sid, None)

        return web.Response(
            status=200,
            body=twiml.encode(),
            content_type=_TWIML_CONTENT_TYPE,
        )

    async def _handle_health(self, request: Any) -> Any:
        """Respond to GET requests (health / webhook connectivity check)."""
        from aiohttp import web

        return web.Response(status=200, text="Twilio Voice adapter OK")

    # ------------------------------------------------------------------
    # REST API — update live call (fallback send path)
    # ------------------------------------------------------------------

    async def _update_call(self, call_sid: str, text: str) -> str | None:
        """Update an active Twilio call's TwiML via the REST API.

        Used by :meth:`send` when there is no pending future for *call_sid*
        (e.g. proactive mid-call updates).  The call must still be active.
        Returns *call_sid* on success, ``None`` on error.
        """
        if not self._account_sid or not self._auth_token:
            logger.warning("twilio_voice.update_call: credentials not configured")
            return None
        try:
            import httpx

            url = (
                f"{_TWILIO_BASE}/Accounts/{self._account_sid}"
                f"/Calls/{call_sid}.json"
            )
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    data={"Twiml": self._twiml_error(text)},
                    auth=(self._account_sid, self._auth_token),
                    timeout=15.0,
                )
                resp.raise_for_status()
                return call_sid
        except Exception as exc:
            logger.error(
                "twilio_voice.update_call_error CallSid=%s: %s", call_sid, exc
            )
            return None

    # ------------------------------------------------------------------
    # Config schema
    # ------------------------------------------------------------------

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "required": ["account_sid", "auth_token"],
            "properties": {
                "account_sid": {
                    "type": "string",
                    "description": "Twilio account SID",
                },
                "auth_token": {
                    "type": "string",
                    "description": "Twilio auth token for signature verification and REST API",
                },
                "host": {
                    "type": "string",
                    "default": "0.0.0.0",
                    "description": "Webhook server bind host",
                },
                "port": {
                    "type": "integer",
                    "default": 8088,
                    "description": "Webhook server port",
                },
                "incoming_path": {
                    "type": "string",
                    "default": "/webhook/twilio_voice/call",
                    "description": "URL path for incoming call webhook",
                },
                "transcript_path": {
                    "type": "string",
                    "default": "/webhook/twilio_voice/transcript",
                    "description": "URL path for speech transcription webhook",
                },
                "greeting": {
                    "type": "string",
                    "default": "Hello! How can I help you?",
                    "description": "Opening words spoken to the caller",
                },
                "voice": {
                    "type": "string",
                    "default": "alice",
                    "description": "Twilio TTS voice name (e.g. 'alice', 'Polly.Joanna')",
                },
                "language": {
                    "type": "string",
                    "default": "en-US",
                    "description": "BCP-47 language tag for speech recognition and synthesis",
                },
                "response_timeout": {
                    "type": "number",
                    "default": 25.0,
                    "description": "Seconds to wait for the AI handler to call send()",
                },
                "speech_timeout": {
                    "type": "string",
                    "default": "auto",
                    "description": "Twilio speechTimeout value ('auto' or number of seconds)",
                },
            },
        }
