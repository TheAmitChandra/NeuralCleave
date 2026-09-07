"""Exercise authentication at real gateway WebSocket handshake boundaries."""

from urllib.parse import urlencode

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from neuralcleave.config import GatewayConfig, NeuralCleaveConfig
from neuralcleave.gateway.main import create_app

PATHS = ["/ws", "/ws/voice", "/ws/canvas", "/ws/terminal"]


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("query", ["", "?token=wrong"])
def test_protected_sockets_reject_missing_or_wrong_key(path, query):
    client = TestClient(create_app(NeuralCleaveConfig(gateway=GatewayConfig(api_key="secret"))))
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect(path + query):
            pytest.fail("Unauthenticated connection accepted")
    assert error.value.code == 1008


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize("transport", ["query", "header"])
def test_protected_sockets_accept_correct_key(path, transport, monkeypatch):
    monkeypatch.setattr("neuralcleave.gateway.websocket.get_runtime", lambda: object())
    key = "secret + / & ="
    client = TestClient(create_app(NeuralCleaveConfig(gateway=GatewayConfig(api_key=key))))
    query = "?" + urlencode({"token": key}) if transport == "query" else ""
    headers = {"X-API-Key": key} if transport == "header" else {}
    with client.websocket_connect(path + query, headers=headers) as socket:
        if path != "/ws/voice":
            assert socket.receive_json()["type"] in {"hello", "ready", "state", "error"}


@pytest.mark.parametrize("path", PATHS)
def test_correct_key_does_not_bypass_origin_check(path):
    client = TestClient(create_app(NeuralCleaveConfig(gateway=GatewayConfig(api_key="secret"))))
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path + "?token=secret", headers={"Origin": "https://untrusted.invalid"}):
            pytest.fail("Untrusted origin accepted")


def test_api_keys_are_scoped_to_each_app():
    first = TestClient(create_app(NeuralCleaveConfig(gateway=GatewayConfig(api_key="first"))))
    second = TestClient(create_app(NeuralCleaveConfig(gateway=GatewayConfig(api_key="second"))))
    for client, key in [(first, "first"), (second, "second")]:
        with client.websocket_connect("/ws?token=" + key) as socket:
            assert socket.receive_json()["type"] == "hello"


def test_keyless_local_gateway_remains_usable():
    client = TestClient(create_app(NeuralCleaveConfig()))
    with client.websocket_connect("/ws") as socket:
        assert socket.receive_json()["type"] == "hello"
