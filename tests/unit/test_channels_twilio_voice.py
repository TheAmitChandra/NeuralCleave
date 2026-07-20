"""Unit tests for neuralcleave.channels.twilio_voice — TwilioVoiceAdapter.

Covers:
  - Construction / config parsing / defaults
  - is_connected lifecycle
  - connect() / disconnect() — server setup, pending future cancellation
  - _verify_signature() — HMAC-SHA1, sorted params, permissive mode
  - TwiML helpers — _twiml_gather, _twiml_say_and_gather, _twiml_error
  - _handle_incoming() — TwiML response, greeting, Gather, sig check
  - _handle_transcript() — dispatch, Future resolution, timeout, empty speech,
    sig check, raw preserved, multi-turn Gather
  - _handle_health() — GET endpoint
  - send() — resolve pending future, fallback _update_call, empty target
  - _update_call() — REST API, credentials, HTTP/network errors
  - ping() — success, no credentials, HTTP error, network error
  - get_config_schema() — shape and required fields
  - Constants
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.twilio_voice import (
    _TWILIO_BASE,
    _TWIML_CONTENT_TYPE,
    _TWIML_DECLARATION,
    TwilioVoiceAdapter,
)

# ===========================================================================
# Helpers / factories
# ===========================================================================


def make_adapter(**overrides: Any) -> TwilioVoiceAdapter:
    cfg: dict[str, Any] = {
        "account_sid": "AC_test_sid",
        "auth_token": "test_auth_token",
        **overrides,
    }
    return TwilioVoiceAdapter(cfg)


def make_incoming_params(
    call_sid: str = "CA_call_001",
    caller: str = "+15551234567",
    to: str = "+15557654321",
    status: str = "ringing",
) -> dict[str, str]:
    return {
        "CallSid": call_sid,
        "From": caller,
        "To": to,
        "CallStatus": status,
        "Direction": "inbound",
        "AccountSid": "AC_test_sid",
    }


def make_transcript_params(
    call_sid: str = "CA_call_001",
    speech: str = "What is the weather today?",
    caller: str = "+15551234567",
    confidence: str = "0.97",
) -> dict[str, str]:
    return {
        "CallSid": call_sid,
        "SpeechResult": speech,
        "From": caller,
        "Confidence": confidence,
        "AccountSid": "AC_test_sid",
    }


def make_twilio_signature(url: str, params: dict, auth_token: str) -> str:
    s = url
    for key in sorted(params.keys()):
        s += key + params[key]
    mac = hmac.new(auth_token.encode(), s.encode(), hashlib.sha1).digest()
    return base64.b64encode(mac).decode()


def fake_form_request(
    params: dict[str, str],
    headers: dict[str, str] | None = None,
    url: str = "https://example.com/webhook/twilio_voice/call",
) -> MagicMock:
    req = MagicMock()
    req.post = AsyncMock(return_value=params)
    req.headers = headers or {}
    mock_url = MagicMock()
    mock_url.__str__ = lambda self: url
    req.url = mock_url
    return req


def fake_bad_post_request() -> MagicMock:
    req = MagicMock()
    req.post = AsyncMock(side_effect=ValueError("bad form data"))
    req.headers = {}
    mock_url = MagicMock()
    mock_url.__str__ = lambda self: "https://example.com/"
    req.url = mock_url
    return req


def fake_response(status: int = 200, json_data: dict | None = None) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json = MagicMock(return_value=json_data or {})
    resp.raise_for_status = MagicMock()
    if status >= 400:
        import httpx
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def fake_http_client(response: MagicMock) -> MagicMock:
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


# ===========================================================================
# 1. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_account_sid_empty(self):
        assert TwilioVoiceAdapter({})._account_sid == ""

    def test_default_auth_token_empty(self):
        assert TwilioVoiceAdapter({})._auth_token == ""

    def test_default_host(self):
        assert make_adapter()._host == "0.0.0.0"

    def test_default_port(self):
        assert make_adapter()._port == 8088

    def test_default_incoming_path(self):
        assert make_adapter()._incoming_path == "/webhook/twilio_voice/call"

    def test_default_transcript_path(self):
        assert make_adapter()._transcript_path == "/webhook/twilio_voice/transcript"

    def test_default_greeting(self):
        assert make_adapter()._greeting == "Hello! How can I help you?"

    def test_default_voice(self):
        assert make_adapter()._voice == "alice"

    def test_default_language(self):
        assert make_adapter()._language == "en-US"

    def test_default_response_timeout(self):
        assert make_adapter()._response_timeout == 25.0

    def test_default_speech_timeout(self):
        assert make_adapter()._speech_timeout == "auto"

    def test_default_runner_none(self):
        assert make_adapter()._runner is None

    def test_default_pending_empty(self):
        assert make_adapter()._pending == {}

    def test_custom_account_sid(self):
        assert make_adapter(account_sid="AC_custom")._account_sid == "AC_custom"

    def test_custom_auth_token(self):
        assert make_adapter(auth_token="tok-xyz")._auth_token == "tok-xyz"

    def test_custom_host(self):
        assert make_adapter(host="127.0.0.1")._host == "127.0.0.1"

    def test_custom_port_int(self):
        assert make_adapter(port=9090)._port == 9090

    def test_custom_port_string_coerced(self):
        assert make_adapter(port="9091")._port == 9091

    def test_custom_incoming_path(self):
        assert make_adapter(incoming_path="/voice/in")._incoming_path == "/voice/in"

    def test_custom_transcript_path(self):
        assert make_adapter(transcript_path="/voice/speech")._transcript_path == "/voice/speech"

    def test_custom_greeting(self):
        assert make_adapter(greeting="Hi there!")._greeting == "Hi there!"

    def test_custom_voice(self):
        assert make_adapter(voice="Polly.Joanna")._voice == "Polly.Joanna"

    def test_custom_language(self):
        assert make_adapter(language="es-ES")._language == "es-ES"

    def test_custom_response_timeout(self):
        assert make_adapter(response_timeout=10.0)._response_timeout == 10.0

    def test_response_timeout_coerced_to_float(self):
        assert isinstance(make_adapter(response_timeout=30)._response_timeout, float)

    def test_custom_speech_timeout(self):
        assert make_adapter(speech_timeout="5")._speech_timeout == "5"

    def test_channel_id(self):
        assert TwilioVoiceAdapter.channel_id == "twilio_voice"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "twilio_voice"


# ===========================================================================
# 2. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_after_runner_set(self):
        a = make_adapter()
        a._runner = MagicMock()
        assert a.is_connected

    def test_not_connected_after_runner_cleared(self):
        a = make_adapter()
        a._runner = MagicMock()
        a._runner = None
        assert not a.is_connected


# ===========================================================================
# 3. connect() / disconnect()
# ===========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_sets_runner(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        assert a._runner is mock_runner

    @pytest.mark.asyncio
    async def test_connect_calls_setup(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        mock_runner.setup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connect_starts_site(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        mock_site = AsyncMock()
        with (
            patch("aiohttp.web.Application"),
            patch("aiohttp.web.AppRunner", return_value=mock_runner),
            patch("aiohttp.web.TCPSite", return_value=mock_site),
        ):
            await a.connect()
        mock_site.start.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_runner(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_disconnect_calls_cleanup(self):
        a = make_adapter()
        mock_runner = AsyncMock()
        a._runner = mock_runner
        await a.disconnect()
        mock_runner.cleanup.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_cancels_pending_futures(self):
        a = make_adapter()
        future: asyncio.Future[str] = asyncio.Future()
        a._pending["CA_test"] = future
        a._runner = AsyncMock()
        await a.disconnect()
        assert future.cancelled()

    @pytest.mark.asyncio
    async def test_disconnect_clears_pending_dict(self):
        a = make_adapter()
        a._pending["CA_test"] = asyncio.Future()
        a._runner = AsyncMock()
        await a.disconnect()
        assert a._pending == {}

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self):
        a = make_adapter()
        await a.disconnect()
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_double_disconnect_safe(self):
        a = make_adapter()
        a._runner = AsyncMock()
        await a.disconnect()
        await a.disconnect()
        assert a._runner is None

    @pytest.mark.asyncio
    async def test_disconnect_skips_done_futures(self):
        a = make_adapter()
        done_future: asyncio.Future[str] = asyncio.Future()
        done_future.set_result("done")
        a._pending["CA_done"] = done_future
        a._runner = AsyncMock()
        await a.disconnect()
        assert not done_future.cancelled()


# ===========================================================================
# 4. _verify_signature()
# ===========================================================================


class TestVerifySignature:
    _URL = "https://mybot.example.com/webhook/twilio_voice/call"
    _PARAMS = {"CallSid": "CA001", "From": "+15551234567"}
    _TOKEN = "test_auth_token"

    def _sig(self, url: str = _URL, params: dict = _PARAMS, token: str = _TOKEN) -> str:
        return make_twilio_signature(url, params, token)

    def test_valid_signature_returns_true(self):
        a = make_adapter(auth_token=self._TOKEN)
        assert a._verify_signature(self._URL, self._PARAMS, self._sig()) is True

    def test_wrong_signature_returns_false(self):
        a = make_adapter(auth_token=self._TOKEN)
        assert a._verify_signature(self._URL, self._PARAMS, "bad-sig") is False

    def test_empty_signature_returns_false(self):
        a = make_adapter(auth_token=self._TOKEN)
        assert a._verify_signature(self._URL, self._PARAMS, "") is False

    def test_no_auth_token_permissive_true(self):
        a = make_adapter(auth_token="")
        assert a._verify_signature(self._URL, self._PARAMS, "anything") is True

    def test_no_auth_token_empty_sig_permissive(self):
        a = make_adapter(auth_token="")
        assert a._verify_signature(self._URL, {}, "") is True

    def test_different_token_returns_false(self):
        a = make_adapter(auth_token="correct-token")
        sig = make_twilio_signature(self._URL, self._PARAMS, "wrong-token")
        assert a._verify_signature(self._URL, self._PARAMS, sig) is False

    def test_tampered_url_returns_false(self):
        a = make_adapter(auth_token=self._TOKEN)
        sig = self._sig()
        assert a._verify_signature("https://evil.com/path", self._PARAMS, sig) is False

    def test_sorted_params_order(self):
        a = make_adapter(auth_token=self._TOKEN)
        params = {"Zoo": "z", "Alpha": "a", "Middle": "m"}
        sig = make_twilio_signature(self._URL, params, self._TOKEN)
        assert a._verify_signature(self._URL, params, sig) is True

    def test_empty_params(self):
        a = make_adapter(auth_token=self._TOKEN)
        sig = make_twilio_signature(self._URL, {}, self._TOKEN)
        assert a._verify_signature(self._URL, {}, sig) is True

    def test_additional_param_breaks_sig(self):
        a = make_adapter(auth_token=self._TOKEN)
        sig = self._sig()
        tampered = {**self._PARAMS, "Extra": "field"}
        assert a._verify_signature(self._URL, tampered, sig) is False

    def test_constant_time_compare(self):
        a = make_adapter(auth_token=self._TOKEN)
        correct = self._sig()
        flipped = correct[:-1] + ("A" if correct[-1] != "A" else "B")
        assert a._verify_signature(self._URL, self._PARAMS, flipped) is False

    def test_unicode_params(self):
        a = make_adapter(auth_token=self._TOKEN)
        params = {"Text": "こんにちは", "From": "+81901234567"}
        sig = make_twilio_signature(self._URL, params, self._TOKEN)
        assert a._verify_signature(self._URL, params, sig) is True


# ===========================================================================
# 5. TwiML helpers
# ===========================================================================


class TestTwiMLHelpers:
    def test_twiml_gather_has_xml_declaration(self):
        a = make_adapter()
        assert _TWIML_DECLARATION in a._twiml_gather()

    def test_twiml_gather_has_response_tag(self):
        a = make_adapter()
        assert "<Response>" in a._twiml_gather()
        assert "</Response>" in a._twiml_gather()

    def test_twiml_gather_has_gather_tag(self):
        a = make_adapter()
        assert "<Gather" in a._twiml_gather()

    def test_twiml_gather_speech_input(self):
        a = make_adapter()
        assert 'input="speech"' in a._twiml_gather()

    def test_twiml_gather_uses_transcript_path(self):
        a = make_adapter(transcript_path="/voice/speech")
        assert '/voice/speech' in a._twiml_gather()

    def test_twiml_gather_with_say_text(self):
        a = make_adapter()
        result = a._twiml_gather(say_text="Please speak now.")
        assert "Please speak now." in result
        assert "<Say" in result

    def test_twiml_gather_without_say_text_no_say_tag(self):
        a = make_adapter()
        result = a._twiml_gather()
        assert "<Say" not in result

    def test_twiml_gather_xml_escaping(self):
        a = make_adapter()
        result = a._twiml_gather(say_text="Say <hello> & goodbye")
        assert "&lt;hello&gt;" in result
        assert "&amp;" in result

    def test_twiml_gather_language_attr(self):
        a = make_adapter(language="fr-FR")
        assert 'language="fr-FR"' in a._twiml_gather()

    def test_twiml_gather_voice_attr(self):
        a = make_adapter(voice="Polly.Joanna")
        result = a._twiml_gather(say_text="Hi")
        assert 'voice="Polly.Joanna"' in result

    def test_twiml_say_and_gather_contains_text(self):
        a = make_adapter()
        assert "Hello, world!" in a._twiml_say_and_gather("Hello, world!")

    def test_twiml_say_and_gather_has_gather(self):
        a = make_adapter()
        assert "<Gather" in a._twiml_say_and_gather("hi")

    def test_twiml_say_and_gather_xml_escaping(self):
        a = make_adapter()
        result = a._twiml_say_and_gather("Price is $10 & tax")
        assert "$10 &amp; tax" in result

    def test_twiml_say_and_gather_has_hangup(self):
        a = make_adapter()
        assert "<Hangup/>" in a._twiml_say_and_gather("bye")

    def test_twiml_error_contains_message(self):
        a = make_adapter()
        result = a._twiml_error("Goodbye!")
        assert "Goodbye!" in result

    def test_twiml_error_has_hangup(self):
        a = make_adapter()
        assert "<Hangup/>" in a._twiml_error()

    def test_twiml_error_no_gather(self):
        a = make_adapter()
        assert "<Gather" not in a._twiml_error()

    def test_twiml_error_default_message(self):
        a = make_adapter()
        result = a._twiml_error()
        assert "Sorry" in result or "went wrong" in result

    def test_twiml_error_xml_escaping(self):
        a = make_adapter()
        result = a._twiml_error("A & B <test>")
        assert "&amp;" in result
        assert "&lt;" in result


# ===========================================================================
# 6. _handle_incoming()
# ===========================================================================


class TestHandleIncoming:
    @pytest.mark.asyncio
    async def test_returns_200(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_content_type_is_xml(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert resp.content_type == _TWIML_CONTENT_TYPE

    @pytest.mark.asyncio
    async def test_response_contains_greeting(self):
        a = make_adapter(auth_token="", greeting="Welcome to NeuralCleave!")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert b"Welcome to NeuralCleave!" in resp.body

    @pytest.mark.asyncio
    async def test_response_contains_gather(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert b"<Gather" in resp.body

    @pytest.mark.asyncio
    async def test_gather_points_to_transcript_path(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert b"/webhook/twilio_voice/transcript" in resp.body

    @pytest.mark.asyncio
    async def test_bad_signature_returns_400(self):
        a = make_adapter()
        params = make_incoming_params()
        req = fake_form_request(params, headers={"X-Twilio-Signature": "bad-sig"})
        resp = await a._handle_incoming(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_valid_signature_accepted(self):
        a = make_adapter()
        params = make_incoming_params()
        url = "https://example.com/webhook/twilio_voice/call"
        sig = make_twilio_signature(url, params, "test_auth_token")
        req = fake_form_request(params, headers={"X-Twilio-Signature": sig}, url=url)
        resp = await a._handle_incoming(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_no_auth_token_accepts_all(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params(), headers={})
        resp = await a._handle_incoming(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_bad_form_data_returns_200_gracefully(self):
        a = make_adapter(auth_token="")
        req = fake_bad_post_request()
        resp = await a._handle_incoming(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_response_has_xml_declaration(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert b"<?xml" in resp.body

    @pytest.mark.asyncio
    async def test_response_has_hangup(self):
        a = make_adapter(auth_token="")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        assert b"<Hangup/>" in resp.body


# ===========================================================================
# 7. _handle_transcript()
# ===========================================================================


class TestHandleTranscript:
    @pytest.mark.asyncio
    async def test_empty_speech_returns_try_again_twiml(self):
        a = make_adapter(auth_token="")
        params = make_transcript_params(speech="")
        req = fake_form_request(params)
        resp = await a._handle_transcript(req)
        assert resp.status == 200
        assert b"catch" in resp.body

    @pytest.mark.asyncio
    async def test_whitespace_speech_returns_try_again_twiml(self):
        a = make_adapter(auth_token="")
        params = {**make_transcript_params(), "SpeechResult": "   "}
        req = fake_form_request(params)
        resp = await a._handle_transcript(req)
        assert b"catch" in resp.body

    @pytest.mark.asyncio
    async def test_dispatches_inbound_message(self):
        a = make_adapter(auth_token="", response_timeout=0.05)
        msgs: list = []

        async def handler(msg):
            msgs.append(msg)

        a.on_message(handler)
        params = make_transcript_params(speech="Hello AI")
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert len(msgs) == 1
        assert msgs[0].text == "Hello AI"

    @pytest.mark.asyncio
    async def test_dispatched_message_channel(self):
        a = make_adapter(auth_token="", response_timeout=0.05)
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        req = fake_form_request(make_transcript_params())
        await a._handle_transcript(req)
        assert msgs[0].channel == "twilio_voice"

    @pytest.mark.asyncio
    async def test_dispatched_message_sender_id_from_from(self):
        a = make_adapter(auth_token="", response_timeout=0.05)
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_transcript_params(caller="+15559876543")
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert msgs[0].sender_id == "+15559876543"

    @pytest.mark.asyncio
    async def test_dispatched_message_thread_id_is_call_sid(self):
        a = make_adapter(auth_token="", response_timeout=0.05)
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_transcript_params(call_sid="CA_unique_001")
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert msgs[0].thread_id == "CA_unique_001"

    @pytest.mark.asyncio
    async def test_dispatched_message_raw_has_params(self):
        a = make_adapter(auth_token="", response_timeout=0.05)
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        params = make_transcript_params()
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert msgs[0].raw["CallSid"] == "CA_call_001"

    @pytest.mark.asyncio
    async def test_future_created_in_pending(self):
        a = make_adapter(auth_token="", response_timeout=0.05)

        async def handler(msg):
            pass

        a.on_message(handler)
        params = make_transcript_params(call_sid="CA_future_test")
        req = fake_form_request(params)
        task = asyncio.create_task(a._handle_transcript(req))
        await asyncio.sleep(0)
        assert "CA_future_test" in a._pending
        await task

    @pytest.mark.asyncio
    async def test_future_removed_after_response(self):
        a = make_adapter(auth_token="", response_timeout=2.0)
        params = make_transcript_params(call_sid="CA_cleanup")

        async def handler(msg):
            await a.send("CA_cleanup", "Done")

        a.on_message(handler)
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert "CA_cleanup" not in a._pending

    @pytest.mark.asyncio
    async def test_future_removed_after_timeout(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        a.on_message(lambda m: None)
        params = make_transcript_params(call_sid="CA_timeout")
        req = fake_form_request(params)
        await a._handle_transcript(req)
        assert "CA_timeout" not in a._pending

    @pytest.mark.asyncio
    async def test_response_contains_ai_reply_in_say(self):
        a = make_adapter(auth_token="", response_timeout=2.0)

        async def handler(msg):
            await a.send(msg.thread_id, "The weather is sunny!")

        a.on_message(handler)
        params = make_transcript_params()
        req = fake_form_request(params)
        resp = await a._handle_transcript(req)
        assert b"The weather is sunny!" in resp.body

    @pytest.mark.asyncio
    async def test_response_has_gather_for_next_turn(self):
        a = make_adapter(auth_token="", response_timeout=2.0)

        async def handler(msg):
            await a.send(msg.thread_id, "Here is your answer.")

        a.on_message(handler)
        req = fake_form_request(make_transcript_params())
        resp = await a._handle_transcript(req)
        assert b"<Gather" in resp.body

    @pytest.mark.asyncio
    async def test_timeout_returns_error_twiml(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        a.on_message(lambda m: None)
        req = fake_form_request(make_transcript_params())
        resp = await a._handle_transcript(req)
        assert resp.status == 200
        assert b"Hangup" in resp.body

    @pytest.mark.asyncio
    async def test_bad_signature_returns_400(self):
        a = make_adapter()
        params = make_transcript_params()
        req = fake_form_request(params, headers={"X-Twilio-Signature": "bad-sig"})
        resp = await a._handle_transcript(req)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_no_auth_token_accepts_all(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        a.on_message(lambda m: None)
        req = fake_form_request(make_transcript_params(), headers={})
        resp = await a._handle_transcript(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_bad_form_data_no_crash(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        a.on_message(lambda m: None)
        req = fake_bad_post_request()
        resp = await a._handle_transcript(req)
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_content_type_xml(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        a.on_message(lambda m: None)
        req = fake_form_request(make_transcript_params())
        resp = await a._handle_transcript(req)
        assert resp.content_type == _TWIML_CONTENT_TYPE

    @pytest.mark.asyncio
    async def test_multiturn_second_call_gets_fresh_future(self):
        a = make_adapter(auth_token="", response_timeout=2.0)
        replies = ["First reply", "Second reply"]
        call_count = 0

        async def handler(msg):
            nonlocal call_count
            await a.send(msg.thread_id, replies[call_count])
            call_count += 1

        a.on_message(handler)
        req1 = fake_form_request(make_transcript_params(speech="Question one"))
        req2 = fake_form_request(make_transcript_params(speech="Question two"))
        resp1 = await a._handle_transcript(req1)
        resp2 = await a._handle_transcript(req2)
        assert b"First reply" in resp1.body
        assert b"Second reply" in resp2.body


# ===========================================================================
# 8. _handle_health()
# ===========================================================================


class TestHandleHealth:
    @pytest.mark.asyncio
    async def test_health_returns_200(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_health_body_contains_ok(self):
        a = make_adapter()
        resp = await a._handle_health(MagicMock())
        assert b"OK" in resp.body or b"Twilio" in resp.body


# ===========================================================================
# 9. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        result = await make_adapter().send("", "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolves_pending_future(self):
        a = make_adapter()
        future: asyncio.Future[str] = asyncio.Future()
        a._pending["CA_001"] = future
        result = await a.send("CA_001", "response text")
        assert result == "CA_001"
        assert future.result() == "response text"

    @pytest.mark.asyncio
    async def test_pending_future_removed_only_when_transcript_completes(self):
        a = make_adapter()
        future: asyncio.Future[str] = asyncio.Future()
        a._pending["CA_001"] = future
        await a.send("CA_001", "hi")
        assert future.done()

    @pytest.mark.asyncio
    async def test_no_pending_future_calls_update_call(self):
        a = make_adapter()
        with patch.object(
            a, "_update_call", new=AsyncMock(return_value="CA_999")
        ) as mock_update:
            result = await a.send("CA_999", "proactive")
        mock_update.assert_awaited_once_with("CA_999", "proactive")
        assert result == "CA_999"

    @pytest.mark.asyncio
    async def test_done_future_falls_through_to_update_call(self):
        a = make_adapter()
        done_future: asyncio.Future[str] = asyncio.Future()
        done_future.set_result("already done")
        a._pending["CA_done"] = done_future
        with patch.object(
            a, "_update_call", new=AsyncMock(return_value="CA_done")
        ) as mock_update:
            result = await a.send("CA_done", "new message")
        mock_update.assert_awaited_once()
        assert result == "CA_done"

    @pytest.mark.asyncio
    async def test_send_returns_none_on_update_fail(self):
        a = make_adapter()
        with patch.object(a, "_update_call", new=AsyncMock(return_value=None)):
            result = await a.send("CA_fail", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_send_does_not_call_update_when_pending_resolved(self):
        a = make_adapter()
        future: asyncio.Future[str] = asyncio.Future()
        a._pending["CA_001"] = future
        with patch.object(a, "_update_call", new=AsyncMock()) as mock_update:
            await a.send("CA_001", "reply")
        mock_update.assert_not_awaited()


# ===========================================================================
# 10. _update_call()
# ===========================================================================


class TestUpdateCall:
    @pytest.mark.asyncio
    async def test_no_account_sid_returns_none(self):
        a = make_adapter(account_sid="")
        result = await a._update_call("CA_001", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_no_auth_token_returns_none(self):
        a = make_adapter(auth_token="")
        result = await a._update_call("CA_001", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_success_returns_call_sid(self):
        a = make_adapter()
        resp = fake_response(200, {"sid": "CA_001", "status": "in-progress"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a._update_call("CA_001", "hello")
        assert result == "CA_001"

    @pytest.mark.asyncio
    async def test_uses_correct_url(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._update_call("CA_001", "hi")
        called_url = client.post.call_args[0][0]
        assert "AC_test_sid" in called_url
        assert "CA_001" in called_url

    @pytest.mark.asyncio
    async def test_uses_basic_auth(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._update_call("CA_001", "hi")
        auth = client.post.call_args[1]["auth"]
        assert auth == ("AC_test_sid", "test_auth_token")

    @pytest.mark.asyncio
    async def test_sends_twiml_in_data(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a._update_call("CA_001", "goodbye")
        data = client.post.call_args[1]["data"]
        assert "Twiml" in data
        assert "goodbye" in data["Twiml"]

    @pytest.mark.asyncio
    async def test_http_error_returns_none(self):
        a = make_adapter()
        resp = fake_response(404, {})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            result = await a._update_call("CA_001", "hi")
        assert result is None

    @pytest.mark.asyncio
    async def test_network_error_returns_none(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            result = await a._update_call("CA_001", "hi")
        assert result is None


# ===========================================================================
# 11. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_account_sid_returns_false(self):
        assert await make_adapter(account_sid="").ping() is False

    @pytest.mark.asyncio
    async def test_no_auth_token_returns_false(self):
        assert await make_adapter(auth_token="").ping() is False

    @pytest.mark.asyncio
    async def test_success_returns_true(self):
        a = make_adapter()
        resp = fake_response(200, {"sid": "AC_test_sid", "status": "active"})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            assert await a.ping() is True

    @pytest.mark.asyncio
    async def test_401_returns_false(self):
        a = make_adapter()
        resp = fake_response(401, {})
        with patch("httpx.AsyncClient", return_value=fake_http_client(resp)):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_network_error_returns_false(self):
        a = make_adapter()
        client = AsyncMock()
        client.__aenter__ = AsyncMock(side_effect=ConnectionError("fail"))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch("httpx.AsyncClient", return_value=client):
            assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_uses_account_sid_url(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        url = client.get.call_args[0][0]
        assert "AC_test_sid" in url

    @pytest.mark.asyncio
    async def test_uses_basic_auth(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        auth = client.get.call_args[1]["auth"]
        assert auth == ("AC_test_sid", "test_auth_token")

    @pytest.mark.asyncio
    async def test_timeout_5s(self):
        a = make_adapter()
        resp = fake_response(200, {})
        client = fake_http_client(resp)
        with patch("httpx.AsyncClient", return_value=client):
            await a.ping()
        assert client.get.call_args[1]["timeout"] == 5.0


# ===========================================================================
# 12. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_account_sid(self):
        assert "account_sid" in make_adapter().get_config_schema()["required"]

    def test_required_has_auth_token(self):
        assert "auth_token" in make_adapter().get_config_schema()["required"]

    def test_properties_has_all_keys(self):
        props = make_adapter().get_config_schema()["properties"]
        for key in (
            "account_sid", "auth_token", "host", "port",
            "incoming_path", "transcript_path", "greeting",
            "voice", "language", "response_timeout", "speech_timeout",
        ):
            assert key in props, f"Missing property: {key}"

    def test_port_default(self):
        assert make_adapter().get_config_schema()["properties"]["port"]["default"] == 8088

    def test_voice_default(self):
        assert make_adapter().get_config_schema()["properties"]["voice"]["default"] == "alice"

    def test_language_default(self):
        assert make_adapter().get_config_schema()["properties"]["language"]["default"] == "en-US"

    def test_response_timeout_default(self):
        assert make_adapter().get_config_schema()["properties"]["response_timeout"]["default"] == 25.0

    def test_greeting_default(self):
        schema = make_adapter().get_config_schema()
        assert "Hello" in schema["properties"]["greeting"]["default"]


# ===========================================================================
# 13. Constants
# ===========================================================================


class TestConstants:
    def test_twilio_base_url(self):
        assert _TWILIO_BASE == "https://api.twilio.com/2010-04-01"

    def test_twiml_content_type(self):
        assert _TWIML_CONTENT_TYPE == "application/xml"

    def test_twiml_declaration(self):
        assert "xml" in _TWIML_DECLARATION.lower()
        assert "UTF-8" in _TWIML_DECLARATION


# ===========================================================================
# 14. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    def test_repr_contains_channel_id(self):
        assert "twilio_voice" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_full_voice_turn_flow(self):
        """End-to-end: incoming call → speech → AI reply → TwiML with reply."""
        a = make_adapter(auth_token="", response_timeout=2.0)

        async def handler(msg):
            await a.send(msg.thread_id, "It is sunny and 72 degrees.")

        a.on_message(handler)

        in_req = fake_form_request(make_incoming_params())
        in_resp = await a._handle_incoming(in_req)
        assert in_resp.status == 200
        assert b"<Gather" in in_resp.body

        tr_req = fake_form_request(make_transcript_params(speech="What's the weather?"))
        tr_resp = await a._handle_transcript(tr_req)
        assert tr_resp.status == 200
        assert b"sunny and 72 degrees" in tr_resp.body
        assert b"<Gather" in tr_resp.body

    @pytest.mark.asyncio
    async def test_concurrent_calls_independent_futures(self):
        a = make_adapter(auth_token="", response_timeout=2.0)
        reply_map = {"CA_111": "Reply for call 111", "CA_222": "Reply for call 222"}

        async def handler(msg):
            await a.send(msg.thread_id, reply_map[msg.thread_id])

        a.on_message(handler)

        req1 = fake_form_request(make_transcript_params(call_sid="CA_111", speech="Question 111"))
        req2 = fake_form_request(make_transcript_params(call_sid="CA_222", speech="Question 222"))
        resp1, resp2 = await asyncio.gather(
            a._handle_transcript(req1),
            a._handle_transcript(req2),
        )
        assert b"Reply for call 111" in resp1.body
        assert b"Reply for call 222" in resp2.body

    @pytest.mark.asyncio
    async def test_greeting_xml_escaped_in_gather_twiml(self):
        a = make_adapter(auth_token="", greeting="Price: <$10> & tax")
        req = fake_form_request(make_incoming_params())
        resp = await a._handle_incoming(req)
        body = resp.body.decode()
        assert "&lt;$10&gt;" in body
        assert "&amp;" in body

    @pytest.mark.asyncio
    async def test_no_handler_does_not_raise_on_transcript(self):
        a = make_adapter(auth_token="", response_timeout=0.01)
        req = fake_form_request(make_transcript_params())
        resp = await a._handle_transcript(req)
        assert resp.status == 200
