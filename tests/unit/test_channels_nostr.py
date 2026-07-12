"""Unit tests for cortexflow_ai.channels.nostr — NostrAdapter.

Covers:
  - secp256k1 primitives: _point_add, _point_mul, _lift_x, _privkey_to_pubkey_hex
  - BIP-340 Schnorr: _tagged_hash, _schnorr_sign, _schnorr_verify
  - ECDH + NIP-04: _ecdh_shared_x, _nip04_encrypt, _nip04_decrypt
  - Nostr event helpers: _event_id, _sign_event, _build_dm_event
  - NostrAdapter constructor / defaults / config parsing
  - is_connected lifecycle
  - connect() / disconnect()
  - _handle_relay_message — EVENT, NOTICE, EOSE, invalid
  - _process_event — kind 4 DM decrypt, kind 1 text, own-event skip, empty text
  - send() — success, no target, no privkey, bad pubkey
  - _broadcast_event — relay OK, relay rejected, timeout-as-sent, no relays, error
  - ping() — success, failure, no relay configured
  - get_config_schema() — shape and required fields
  - Edge / integration cases
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cortexflow_ai.channels.nostr import (
    _G,
    _N,
    _P,
    NostrAdapter,
    _build_dm_event,
    _ecdh_shared_x,
    _event_id,
    _Gx,
    _Gy,
    _lift_x,
    _nip04_decrypt,
    _nip04_encrypt,
    _point_add,
    _point_mul,
    _privkey_to_pubkey_hex,
    _schnorr_sign,
    _schnorr_verify,
    _sign_event,
    _tagged_hash,
)

# ---------------------------------------------------------------------------
# Known test keypairs (secp256k1)
# BIP-340 test vector 1 for Alice
# ---------------------------------------------------------------------------
ALICE_PRIV = "b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef"
ALICE_PUB = "dff1d77f2a671c5f36183726db2341be58feae1da2deced843240f7b502ba659"

# Bob — a distinct keypair derived by the module itself
BOB_PRIV = "0c90fdaa22168c234c4c6628b80dc1cd129024e088a67cc74020bbea63b14e5c7"
BOB_PUB = _privkey_to_pubkey_hex(BOB_PRIV)

# BIP-340 test vector (https://github.com/bitcoin/bips/blob/master/bip-0340.md)
_BIP340_SK = "b7e151628aed2a6abf7158809cf4f3c762e7160f38b4da56a784d9045190cfef"
_BIP340_PK = "dff1d77f2a671c5f36183726db2341be58feae1da2deced843240f7b502ba659"
_BIP340_MSG = bytes.fromhex("243f6a8885a308d313198a2e03707344a4093822299f31d0082efa98ec4e6c89")
_BIP340_AUX = bytes.fromhex("0000000000000000000000000000000000000000000000000000000000000001")
_BIP340_SIG = bytes.fromhex(
    "6896bd60eeae296db48a229ff71dfe071bde413e6d43f917dc8dcf8c78de334"
    "18906d11ac976abccb20b091292bff4ea897efcb639ea871cfa95f6de339e4b0a"
)


def make_adapter(**overrides: Any) -> NostrAdapter:
    cfg: dict[str, Any] = {
        "private_key": ALICE_PRIV,
        "relay_urls": ["wss://relay.example.com"],
        **overrides,
    }
    return NostrAdapter(cfg)


def fake_ws_message(data: Any, msg_type: str = "TEXT") -> MagicMock:
    import aiohttp
    msg = MagicMock()
    msg.type = aiohttp.WSMsgType.TEXT
    msg.data = json.dumps(data) if not isinstance(data, str) else data
    return msg


class _FakeWS:
    """Minimal async context manager + async iterator for WebSocket mocking."""

    def __init__(self, messages: list) -> None:
        self._messages = list(messages)
        self._idx = 0
        self.send_json = AsyncMock()

    async def __aenter__(self) -> "_FakeWS":
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    def __aiter__(self) -> "_FakeWS":
        self._idx = 0
        return self

    async def __anext__(self) -> Any:
        if self._idx >= len(self._messages):
            raise StopAsyncIteration
        msg = self._messages[self._idx]
        self._idx += 1
        return msg


def fake_ws(messages: list) -> _FakeWS:
    return _FakeWS(messages)


def fake_session(ws: _FakeWS) -> MagicMock:
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    session.ws_connect = MagicMock(return_value=ws)
    return session


# ===========================================================================
# 1. secp256k1 primitives
# ===========================================================================


class TestCurveParameters:
    def test_generator_on_curve(self):
        assert (pow(_Gy, 2, _P) - pow(_Gx, 3, _P) - 7) % _P == 0

    def test_p_is_prime_characteristic(self):
        assert pow(2, _P - 1, _P) == 1

    def test_n_is_large(self):
        assert _N > 2**252


class TestPointAdd:
    def test_identity_left(self):
        assert _point_add(None, _G) == _G

    def test_identity_right(self):
        assert _point_add(_G, None) == _G

    def test_both_identity(self):
        assert _point_add(None, None) is None

    def test_point_plus_inverse_is_infinity(self):
        inv_G = (_Gx, _P - _Gy)
        assert _point_add(_G, inv_G) is None

    def test_point_doubled(self):
        result = _point_add(_G, _G)
        assert result is not None
        x2, y2 = result
        assert (y2 * y2 - x2 * x2 * x2 - 7) % _P == 0

    def test_commutativity(self):
        two_g = _point_add(_G, _G)
        three_g = _point_add(two_g, _G)
        three_g_alt = _point_add(_G, two_g)
        assert three_g == three_g_alt

    def test_distinct_points(self):
        two_g = _point_add(_G, _G)
        three_g = _point_add(two_g, _G)
        assert three_g != two_g
        assert three_g != _G


class TestPointMul:
    def test_mul_by_one_is_generator(self):
        assert _point_mul(1) == _G

    def test_mul_by_two_equals_double(self):
        assert _point_mul(2) == _point_add(_G, _G)

    def test_mul_by_n_is_infinity(self):
        assert _point_mul(_N) is None

    def test_commutativity_of_composition(self):
        p3 = _point_mul(3)
        p5 = _point_mul(5)
        p8 = _point_mul(8)
        assert _point_add(p3, p5) == p8

    def test_custom_base_point(self):
        two_g = _point_add(_G, _G)
        result = _point_mul(3, _G)
        assert result == _point_add(two_g, _G)

    def test_mul_result_on_curve(self):
        P = _point_mul(12345)
        assert P is not None
        x, y = P
        assert (y * y - x * x * x - 7) % _P == 0


class TestLiftX:
    def test_generator_x_lifts(self):
        P = _lift_x(_Gx)
        assert P is not None
        assert P[0] == _Gx
        assert P[1] % 2 == 0

    def test_result_on_curve(self):
        P = _lift_x(_Gx)
        x, y = P
        assert (y * y - x * x * x - 7) % _P == 0

    def test_invalid_x_returns_none(self):
        assert _lift_x(0) is None

    def test_known_pubkey_lifts(self):
        x = int(ALICE_PUB, 16)
        P = _lift_x(x)
        assert P is not None
        assert P[0] == x


class TestPrivkeyToPubkey:
    def test_bip340_test_vector(self):
        assert _privkey_to_pubkey_hex(_BIP340_SK).lower() == _BIP340_PK.lower()

    def test_pubkey_is_64_chars(self):
        pub = _privkey_to_pubkey_hex(ALICE_PRIV)
        assert len(pub) == 64

    def test_pubkey_is_hex(self):
        pub = _privkey_to_pubkey_hex(ALICE_PRIV)
        int(pub, 16)  # raises ValueError if not hex

    def test_pubkey_x_on_curve(self):
        x = int(_privkey_to_pubkey_hex(ALICE_PRIV), 16)
        P = _lift_x(x)
        assert P is not None

    def test_different_privkeys_give_different_pubkeys(self):
        assert _privkey_to_pubkey_hex(ALICE_PRIV) != _privkey_to_pubkey_hex(BOB_PRIV)


# ===========================================================================
# 2. BIP-340 Schnorr
# ===========================================================================


class TestTaggedHash:
    def test_returns_32_bytes(self):
        assert len(_tagged_hash("test", b"data")) == 32

    def test_deterministic(self):
        assert _tagged_hash("tag", b"data") == _tagged_hash("tag", b"data")

    def test_different_tags_differ(self):
        assert _tagged_hash("BIP0340/aux", b"x") != _tagged_hash("BIP0340/nonce", b"x")

    def test_different_data_differ(self):
        assert _tagged_hash("tag", b"a") != _tagged_hash("tag", b"b")

    def test_prefixed_with_tag_hash_twice(self):
        tag_hash = hashlib.sha256("BIP0340/aux".encode()).digest()
        expected = hashlib.sha256(tag_hash + tag_hash + b"test").digest()
        assert _tagged_hash("BIP0340/aux", b"test") == expected


class TestSchnorrSign:
    def test_returns_64_bytes(self):
        sig = _schnorr_sign(_BIP340_MSG, _BIP340_SK, _BIP340_AUX)
        assert len(sig) == 64

    def test_bip340_test_vector(self):
        sig = _schnorr_sign(_BIP340_MSG, _BIP340_SK, _BIP340_AUX)
        assert sig.lower() == _BIP340_SIG.lower()

    def test_deterministic_with_aux(self):
        aux = bytes(32)
        s1 = _schnorr_sign(_BIP340_MSG, _BIP340_SK, aux)
        s2 = _schnorr_sign(_BIP340_MSG, _BIP340_SK, aux)
        assert s1 == s2

    def test_different_messages_differ(self):
        msg2 = bytes([1] * 32)
        s1 = _schnorr_sign(_BIP340_MSG, _BIP340_SK, bytes(32))
        s2 = _schnorr_sign(msg2, _BIP340_SK, bytes(32))
        assert s1 != s2

    def test_different_keys_differ(self):
        s1 = _schnorr_sign(_BIP340_MSG, ALICE_PRIV, bytes(32))
        s2 = _schnorr_sign(_BIP340_MSG, BOB_PRIV, bytes(32))
        assert s1 != s2


class TestSchnorrVerify:
    def test_bip340_vector_verifies(self):
        assert _schnorr_verify(_BIP340_MSG, _BIP340_PK, _BIP340_SIG) is True

    def test_sign_then_verify(self):
        msg = bytes(32)
        sig = _schnorr_sign(msg, ALICE_PRIV, bytes(32))
        assert _schnorr_verify(msg, ALICE_PUB, sig) is True

    def test_wrong_pubkey_fails(self):
        msg = bytes(32)
        sig = _schnorr_sign(msg, ALICE_PRIV, bytes(32))
        assert _schnorr_verify(msg, BOB_PUB, sig) is False

    def test_wrong_message_fails(self):
        sig = _schnorr_sign(bytes(32), ALICE_PRIV, bytes(32))
        assert _schnorr_verify(bytes([1] * 32), ALICE_PUB, sig) is False

    def test_tampered_sig_fails(self):
        msg = bytes(32)
        sig = bytearray(_schnorr_sign(msg, ALICE_PRIV, bytes(32)))
        sig[0] ^= 0xFF
        assert _schnorr_verify(msg, ALICE_PUB, bytes(sig)) is False

    def test_wrong_sig_length_fails(self):
        assert _schnorr_verify(bytes(32), ALICE_PUB, b"short") is False

    def test_zero_sig_fails(self):
        assert _schnorr_verify(bytes(32), ALICE_PUB, bytes(64)) is False


# ===========================================================================
# 3. ECDH + NIP-04
# ===========================================================================


class TestEcdhSharedX:
    def test_symmetric(self):
        x1 = _ecdh_shared_x(ALICE_PRIV, BOB_PUB)
        x2 = _ecdh_shared_x(BOB_PRIV, ALICE_PUB)
        assert x1 == x2

    def test_returns_32_bytes(self):
        x = _ecdh_shared_x(ALICE_PRIV, BOB_PUB)
        assert len(x) == 32

    def test_invalid_pubkey_raises(self):
        with pytest.raises(ValueError):
            _ecdh_shared_x(ALICE_PRIV, "0" * 64)

    def test_different_pairs_different_secret(self):
        x1 = _ecdh_shared_x(ALICE_PRIV, BOB_PUB)
        x2 = _ecdh_shared_x(ALICE_PRIV, ALICE_PUB)
        assert x1 != x2


class TestNip04:
    def test_encrypt_decrypt_roundtrip(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "Hello, Bob!")
        pt = _nip04_decrypt(BOB_PRIV, ALICE_PUB, ct)
        assert pt == "Hello, Bob!"

    def test_decrypt_from_recipient_side(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "Secret message")
        assert _nip04_decrypt(BOB_PRIV, ALICE_PUB, ct) == "Secret message"

    def test_encrypted_is_string(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "test")
        assert isinstance(ct, str)

    def test_encrypted_has_iv_separator(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "test")
        assert "?iv=" in ct

    def test_unicode_roundtrip(self):
        msg = "こんにちは世界 🌍"
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, msg)
        pt = _nip04_decrypt(BOB_PRIV, ALICE_PUB, ct)
        assert pt == msg

    def test_empty_string_roundtrip(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "")
        pt = _nip04_decrypt(BOB_PRIV, ALICE_PUB, ct)
        assert pt == ""

    def test_long_message_roundtrip(self):
        msg = "A" * 10000
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, msg)
        pt = _nip04_decrypt(BOB_PRIV, ALICE_PUB, ct)
        assert pt == msg

    def test_nondeterministic_encryption(self):
        ct1 = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "same plaintext")
        ct2 = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "same plaintext")
        assert ct1 != ct2

    def test_bad_content_raises(self):
        with pytest.raises(Exception):
            _nip04_decrypt(BOB_PRIV, ALICE_PUB, "no-iv-separator-here")

    def test_wrong_key_cant_decrypt(self):
        ct = _nip04_encrypt(ALICE_PRIV, BOB_PUB, "private")
        with pytest.raises(Exception):
            _nip04_decrypt(ALICE_PRIV, ALICE_PUB, ct)


# ===========================================================================
# 4. Nostr event helpers
# ===========================================================================


class TestEventId:
    def test_returns_64_char_hex(self):
        event = {
            "pubkey": ALICE_PUB,
            "created_at": 1700000000,
            "kind": 1,
            "tags": [],
            "content": "hello",
        }
        eid = _event_id(event)
        assert len(eid) == 64
        int(eid, 16)

    def test_deterministic(self):
        event = {
            "pubkey": ALICE_PUB,
            "created_at": 1700000000,
            "kind": 1,
            "tags": [],
            "content": "hello",
        }
        assert _event_id(event) == _event_id(event)

    def test_different_content_different_id(self):
        base = {"pubkey": ALICE_PUB, "created_at": 1700000000, "kind": 1, "tags": [], "content": "a"}
        e2 = {**base, "content": "b"}
        assert _event_id(base) != _event_id(e2)

    def test_different_kind_different_id(self):
        base = {"pubkey": ALICE_PUB, "created_at": 1700000000, "kind": 1, "tags": [], "content": ""}
        e4 = {**base, "kind": 4}
        assert _event_id(base) != _event_id(e4)


class TestSignEvent:
    def _base_event(self) -> dict:
        return {
            "pubkey": ALICE_PUB,
            "created_at": 1700000000,
            "kind": 1,
            "tags": [],
            "content": "Hello Nostr!",
        }

    def test_adds_id(self):
        e = _sign_event(self._base_event(), ALICE_PRIV)
        assert "id" in e

    def test_adds_sig(self):
        e = _sign_event(self._base_event(), ALICE_PRIV)
        assert "sig" in e

    def test_sig_is_128_char_hex(self):
        e = _sign_event(self._base_event(), ALICE_PRIV)
        assert len(e["sig"]) == 128
        int(e["sig"], 16)

    def test_id_matches_event_id(self):
        base = self._base_event()
        e = _sign_event(base, ALICE_PRIV)
        assert e["id"] == _event_id(base)

    def test_sig_verifies(self):
        e = _sign_event(self._base_event(), ALICE_PRIV)
        assert _schnorr_verify(bytes.fromhex(e["id"]), ALICE_PUB, bytes.fromhex(e["sig"])) is True


class TestBuildDmEvent:
    def test_kind_is_4(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "hi")
        assert e["kind"] == 4

    def test_pubkey_is_sender(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "hi")
        assert e["pubkey"] == ALICE_PUB

    def test_p_tag_is_recipient(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "hi")
        p_tags = [t for t in e["tags"] if t[0] == "p"]
        assert len(p_tags) == 1
        assert p_tags[0][1] == BOB_PUB

    def test_content_is_encrypted(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "secret")
        assert "?iv=" in e["content"]
        assert "secret" not in e["content"]

    def test_content_decryptable_by_recipient(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "hello bob")
        pt = _nip04_decrypt(BOB_PRIV, ALICE_PUB, e["content"])
        assert pt == "hello bob"

    def test_has_valid_id_and_sig(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "test")
        assert len(e["id"]) == 64
        assert len(e["sig"]) == 128

    def test_sig_verifies(self):
        e = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "verified")
        assert _schnorr_verify(bytes.fromhex(e["id"]), ALICE_PUB, bytes.fromhex(e["sig"])) is True


# ===========================================================================
# 5. Constructor / defaults
# ===========================================================================


class TestConstructor:
    def test_default_no_private_key(self):
        assert NostrAdapter({})._private_key_hex == ""

    def test_default_no_public_key(self):
        assert NostrAdapter({})._public_key_hex == ""

    def test_private_key_set(self):
        assert make_adapter()._private_key_hex == ALICE_PRIV

    def test_public_key_derived(self):
        assert make_adapter()._public_key_hex == ALICE_PUB

    def test_default_relay_urls(self):
        a = NostrAdapter({"private_key": ALICE_PRIV})
        assert "wss://relay.damus.io" in a._relay_urls

    def test_custom_relay_urls(self):
        a = make_adapter(relay_urls=["wss://r1.example.com", "wss://r2.example.com"])
        assert a._relay_urls == ["wss://r1.example.com", "wss://r2.example.com"]

    def test_string_relay_url_coerced_to_list(self):
        a = make_adapter(relay_urls="wss://single.example.com")
        assert a._relay_urls == ["wss://single.example.com"]

    def test_default_subscribe_kinds(self):
        assert make_adapter()._subscribe_kinds == [4]

    def test_custom_subscribe_kinds(self):
        a = make_adapter(subscribe_kinds=[1, 4])
        assert a._subscribe_kinds == [1, 4]

    def test_default_reconnect_delay(self):
        assert make_adapter()._reconnect_delay == 5.0

    def test_custom_reconnect_delay(self):
        a = make_adapter(reconnect_delay=10.0)
        assert a._reconnect_delay == 10.0

    def test_reconnect_delay_coerced_to_float(self):
        a = make_adapter(reconnect_delay=3)
        assert isinstance(a._reconnect_delay, float)

    def test_ping_relay_defaults_to_first(self):
        a = make_adapter(relay_urls=["wss://relay1.example.com", "wss://relay2.example.com"])
        assert a._ping_relay == "wss://relay1.example.com"

    def test_custom_ping_relay(self):
        a = make_adapter(ping_relay="wss://custom-ping.example.com")
        assert a._ping_relay == "wss://custom-ping.example.com"

    def test_ws_task_none_initially(self):
        assert make_adapter()._ws_task is None

    def test_relay_tasks_empty_initially(self):
        assert make_adapter()._relay_tasks == []

    def test_channel_id(self):
        assert NostrAdapter.channel_id == "nostr"

    def test_channel_id_on_instance(self):
        assert make_adapter().channel_id == "nostr"

    def test_bad_private_key_does_not_raise(self):
        a = NostrAdapter({"private_key": "not-a-valid-hex-key"})
        assert a._public_key_hex == ""


# ===========================================================================
# 6. is_connected
# ===========================================================================


class TestIsConnected:
    def test_not_connected_initially(self):
        assert not make_adapter().is_connected

    def test_connected_when_ws_task_set(self):
        a = make_adapter()
        a._ws_task = MagicMock()
        assert a.is_connected

    def test_not_connected_after_task_cleared(self):
        a = make_adapter()
        a._ws_task = MagicMock()
        a._ws_task = None
        assert not a.is_connected


# ===========================================================================
# 7. connect() / disconnect()
# ===========================================================================


class TestLifecycle:
    @pytest.mark.asyncio
    async def test_connect_sets_ws_task(self):
        a = make_adapter()
        with patch.object(a, "_run_all_relays", new=AsyncMock()):
            await a.connect()
        assert a._ws_task is not None
        a._ws_task.cancel()

    @pytest.mark.asyncio
    async def test_disconnect_clears_ws_task(self):
        a = make_adapter()
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        a._stop_event = asyncio.Event()
        await a.disconnect()
        assert a._ws_task is None

    @pytest.mark.asyncio
    async def test_disconnect_sets_stop_event(self):
        a = make_adapter()
        stop = asyncio.Event()
        a._stop_event = stop
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        assert stop.is_set()

    @pytest.mark.asyncio
    async def test_disconnect_safe_when_not_connected(self):
        a = make_adapter()
        await a.disconnect()
        assert a._ws_task is None

    @pytest.mark.asyncio
    async def test_disconnect_cancels_relay_tasks(self):
        a = make_adapter()
        t = MagicMock()
        t.cancel = MagicMock()
        a._relay_tasks = [t]
        a._stop_event = asyncio.Event()
        mock_ws_task = AsyncMock()
        mock_ws_task.cancel = MagicMock()
        a._ws_task = mock_ws_task
        await a.disconnect()
        t.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_clears_relay_tasks(self):
        a = make_adapter()
        a._relay_tasks = [MagicMock()]
        a._stop_event = asyncio.Event()
        mock_task = AsyncMock()
        mock_task.cancel = MagicMock()
        a._ws_task = mock_task
        await a.disconnect()
        assert a._relay_tasks == []


# ===========================================================================
# 8. _handle_relay_message
# ===========================================================================


class TestHandleRelayMessage:
    @pytest.mark.asyncio
    async def test_event_message_calls_process_event(self):
        a = make_adapter()
        event_data = {"kind": 1, "pubkey": BOB_PUB, "content": "hi", "id": "a" * 64, "created_at": 1700000000}
        with patch.object(a, "_process_event", new=AsyncMock()) as mock_proc:
            await a._handle_relay_message(["EVENT", "sub1", event_data])
        mock_proc.assert_awaited_once_with(event_data)

    @pytest.mark.asyncio
    async def test_notice_logged_not_dispatched(self):
        a = make_adapter()
        with patch.object(a, "_process_event", new=AsyncMock()) as mock_proc:
            await a._handle_relay_message(["NOTICE", "relay: hello"])
        mock_proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_eose_ignored(self):
        a = make_adapter()
        with patch.object(a, "_process_event", new=AsyncMock()) as mock_proc:
            await a._handle_relay_message(["EOSE", "sub1"])
        mock_proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_ok_message_ignored(self):
        a = make_adapter()
        with patch.object(a, "_process_event", new=AsyncMock()) as mock_proc:
            await a._handle_relay_message(["OK", "a" * 64, True, ""])
        mock_proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_empty_list_ignored(self):
        a = make_adapter()
        await a._handle_relay_message([])

    @pytest.mark.asyncio
    async def test_non_list_ignored(self):
        a = make_adapter()
        await a._handle_relay_message({"type": "EVENT"})

    @pytest.mark.asyncio
    async def test_event_too_short_no_crash(self):
        a = make_adapter()
        await a._handle_relay_message(["EVENT", "sub1"])


# ===========================================================================
# 9. _process_event
# ===========================================================================


class TestProcessEvent:
    def _make_kind1_event(self, text: str = "hello", pubkey: str = BOB_PUB) -> dict:
        return {
            "kind": 1,
            "pubkey": pubkey,
            "content": text,
            "id": "b" * 64,
            "created_at": 1700000000,
        }

    def _make_kind4_event(self, plaintext: str = "secret dm") -> dict:
        content = _nip04_encrypt(BOB_PRIV, ALICE_PUB, plaintext)
        return {
            "kind": 4,
            "pubkey": BOB_PUB,
            "content": content,
            "id": "c" * 64,
            "created_at": 1700000000,
            "tags": [["p", ALICE_PUB]],
        }

    @pytest.mark.asyncio
    async def test_kind1_dispatches(self):
        a = make_adapter(subscribe_kinds=[1])
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_event(self._make_kind1_event("hello world"))
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "hello world"

    @pytest.mark.asyncio
    async def test_kind1_message_channel(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_event(self._make_kind1_event())
        await asyncio.sleep(0)
        assert msgs[0].channel == "nostr"

    @pytest.mark.asyncio
    async def test_kind1_sender_id_is_pubkey(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_event(self._make_kind1_event(pubkey=BOB_PUB))
        await asyncio.sleep(0)
        assert msgs[0].sender_id == BOB_PUB

    @pytest.mark.asyncio
    async def test_kind1_thread_id_is_event_id(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = self._make_kind1_event()
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].thread_id == event["id"]

    @pytest.mark.asyncio
    async def test_kind4_dm_decrypted(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        await a._process_event(self._make_kind4_event("hello alice!"))
        await asyncio.sleep(0)
        assert len(msgs) == 1
        assert msgs[0].text == "hello alice!"

    @pytest.mark.asyncio
    async def test_own_event_skipped(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = self._make_kind1_event(pubkey=ALICE_PUB)
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_empty_content_skipped(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = {**self._make_kind1_event(), "content": "   "}
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_non_dict_event_ignored(self):
        a = make_adapter()
        await a._process_event("not a dict")

    @pytest.mark.asyncio
    async def test_kind4_bad_encryption_skipped(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = {
            "kind": 4,
            "pubkey": BOB_PUB,
            "content": "not-valid-nip04-content",
            "id": "d" * 64,
            "created_at": 1700000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_kind4_no_privkey_skipped(self):
        a = NostrAdapter({"relay_urls": ["wss://relay.example.com"]})
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = self._make_kind4_event()
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs == []

    @pytest.mark.asyncio
    async def test_raw_contains_full_event(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = self._make_kind1_event("check raw")
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].raw == event

    @pytest.mark.asyncio
    async def test_timestamp_from_created_at(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = {**self._make_kind1_event(), "created_at": 1700000000}
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].timestamp == 1700000000.0


# ===========================================================================
# 10. send()
# ===========================================================================


class TestSend:
    @pytest.mark.asyncio
    async def test_empty_target_returns_none(self):
        assert await make_adapter().send("", "hi") is None

    @pytest.mark.asyncio
    async def test_no_private_key_returns_none(self):
        a = NostrAdapter({"relay_urls": ["wss://relay.example.com"]})
        assert await a.send(BOB_PUB, "hi") is None

    @pytest.mark.asyncio
    async def test_success_returns_event_id(self):
        a = make_adapter()
        with patch.object(a, "_broadcast_event", new=AsyncMock(return_value="a" * 64)):
            result = await a.send(BOB_PUB, "hello")
        assert result == "a" * 64

    @pytest.mark.asyncio
    async def test_broadcast_failure_returns_none(self):
        a = make_adapter()
        with patch.object(a, "_broadcast_event", new=AsyncMock(return_value=None)):
            result = await a.send(BOB_PUB, "hello")
        assert result is None

    @pytest.mark.asyncio
    async def test_calls_broadcast_with_event(self):
        a = make_adapter()
        with patch.object(a, "_broadcast_event", new=AsyncMock(return_value="x" * 64)) as mock:
            await a.send(BOB_PUB, "hello")
        event = mock.call_args[0][0]
        assert event["kind"] == 4
        assert event["pubkey"] == ALICE_PUB

    @pytest.mark.asyncio
    async def test_bad_recipient_pubkey_returns_none(self):
        a = make_adapter()
        result = await a.send("0" * 64, "hi")
        assert result is None


# ===========================================================================
# 11. _broadcast_event
# ===========================================================================


class TestBroadcastEvent:
    def _dummy_event(self) -> dict:
        return {
            "id": "e" * 64,
            "pubkey": ALICE_PUB,
            "created_at": 1700000000,
            "kind": 1,
            "tags": [],
            "content": "test",
            "sig": "f" * 128,
        }

    @pytest.mark.asyncio
    async def test_no_relay_urls_returns_none(self):
        a = make_adapter(relay_urls=[])
        result = await a._broadcast_event(self._dummy_event())
        assert result is None

    @pytest.mark.asyncio
    async def test_relay_ok_true_returns_event_id(self):
        a = make_adapter()
        import aiohttp
        ok_msg = MagicMock()
        ok_msg.type = aiohttp.WSMsgType.TEXT
        ok_msg.data = json.dumps(["OK", "e" * 64, True, ""])
        ws = fake_ws([ok_msg])
        session = fake_session(ws)
        with patch("aiohttp.ClientSession", return_value=session):
            result = await a._broadcast_event(self._dummy_event())
        assert result == "e" * 64

    @pytest.mark.asyncio
    async def test_relay_ok_false_returns_none(self):
        a = make_adapter()
        import aiohttp
        ok_msg = MagicMock()
        ok_msg.type = aiohttp.WSMsgType.TEXT
        ok_msg.data = json.dumps(["OK", "e" * 64, False, "blocked"])
        ws = fake_ws([ok_msg])
        session = fake_session(ws)
        with patch("aiohttp.ClientSession", return_value=session):
            result = await a._broadcast_event(self._dummy_event())
        assert result is None

    @pytest.mark.asyncio
    async def test_relay_connect_error_returns_none(self):
        a = make_adapter()
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.ws_connect = MagicMock(side_effect=ConnectionError("fail"))
        with patch("aiohttp.ClientSession", return_value=session):
            result = await a._broadcast_event(self._dummy_event())
        assert result is None

    @pytest.mark.asyncio
    async def test_sends_event_to_relay(self):
        a = make_adapter()
        import aiohttp
        ok_msg = MagicMock()
        ok_msg.type = aiohttp.WSMsgType.TEXT
        ok_msg.data = json.dumps(["OK", "e" * 64, True, ""])
        ws = fake_ws([ok_msg])
        session = fake_session(ws)
        with patch("aiohttp.ClientSession", return_value=session):
            await a._broadcast_event(self._dummy_event())
        ws.send_json.assert_awaited()
        sent = ws.send_json.call_args[0][0]
        assert sent[0] == "EVENT"


# ===========================================================================
# 12. ping()
# ===========================================================================


class TestPing:
    @pytest.mark.asyncio
    async def test_no_ping_relay_returns_false(self):
        a = make_adapter(relay_urls=[], ping_relay="")
        assert await a.ping() is False

    @pytest.mark.asyncio
    async def test_successful_connect_returns_true(self):
        a = make_adapter()
        ws = fake_ws([])
        session = fake_session(ws)
        with patch("aiohttp.ClientSession", return_value=session):
            result = await a.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_connect_error_returns_false(self):
        a = make_adapter()
        session = AsyncMock()
        session.__aenter__ = AsyncMock(return_value=session)
        session.__aexit__ = AsyncMock(return_value=False)
        session.ws_connect = MagicMock(side_effect=ConnectionError("fail"))
        with patch("aiohttp.ClientSession", return_value=session):
            result = await a.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_sends_req_to_relay(self):
        a = make_adapter()
        ws = fake_ws([])
        session = fake_session(ws)
        with patch("aiohttp.ClientSession", return_value=session):
            await a.ping()
        ws.send_json.assert_awaited()
        sent = ws.send_json.call_args[0][0]
        assert sent[0] == "REQ"


# ===========================================================================
# 13. get_config_schema()
# ===========================================================================


class TestConfigSchema:
    def test_returns_dict(self):
        assert isinstance(make_adapter().get_config_schema(), dict)

    def test_type_is_object(self):
        assert make_adapter().get_config_schema()["type"] == "object"

    def test_required_has_private_key(self):
        assert "private_key" in make_adapter().get_config_schema()["required"]

    def test_properties_has_private_key(self):
        assert "private_key" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_relay_urls(self):
        assert "relay_urls" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_subscribe_kinds(self):
        assert "subscribe_kinds" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_reconnect_delay(self):
        assert "reconnect_delay" in make_adapter().get_config_schema()["properties"]

    def test_properties_has_ping_relay(self):
        assert "ping_relay" in make_adapter().get_config_schema()["properties"]

    def test_relay_urls_default(self):
        default = make_adapter().get_config_schema()["properties"]["relay_urls"]["default"]
        assert isinstance(default, list)
        assert len(default) >= 1

    def test_subscribe_kinds_default(self):
        default = make_adapter().get_config_schema()["properties"]["subscribe_kinds"]["default"]
        assert 4 in default


# ===========================================================================
# 14. Edge / integration cases
# ===========================================================================


class TestEdgeCases:
    @pytest.mark.asyncio
    async def test_full_dm_roundtrip_via_process_event(self):
        """Alice sends a DM; bob's adapter receives and dispatches it plaintext."""
        bob_adapter = make_adapter(
            private_key=BOB_PRIV,
            relay_urls=["wss://relay.example.com"],
        )
        msgs: list = []
        bob_adapter.on_message(lambda m: msgs.append(m))

        # Alice creates the DM event
        event = _build_dm_event(ALICE_PRIV, ALICE_PUB, BOB_PUB, "Hey Bob, secret!")
        await bob_adapter._process_event(event)
        await asyncio.sleep(0)

        assert len(msgs) == 1
        assert msgs[0].text == "Hey Bob, secret!"
        assert msgs[0].sender_id == ALICE_PUB
        assert msgs[0].channel == "nostr"

    def test_repr_contains_channel_id(self):
        assert "nostr" in repr(make_adapter())

    @pytest.mark.asyncio
    async def test_multiple_events_dispatched_independently(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))

        for i in range(5):
            event = {
                "kind": 1,
                "pubkey": BOB_PUB,
                "content": f"message {i}",
                "id": str(i) * 64,
                "created_at": 1700000000 + i,
            }
            await a._process_event(event)
        await asyncio.sleep(0)
        assert len(msgs) == 5
        texts = [m.text for m in msgs]
        for i in range(5):
            assert f"message {i}" in texts

    @pytest.mark.asyncio
    async def test_kind1_with_unicode_content(self):
        a = make_adapter()
        msgs: list = []
        a.on_message(lambda m: msgs.append(m))
        event = {
            "kind": 1,
            "pubkey": BOB_PUB,
            "content": "こんにちは 🌸",
            "id": "a" * 64,
            "created_at": 1700000000,
        }
        await a._process_event(event)
        await asyncio.sleep(0)
        assert msgs[0].text == "こんにちは 🌸"
