"""Tests for JsonRpcRequest parsing from dict."""

from __future__ import annotations

import pytest

from neuralcleave.mcp.protocol import JsonRpcRequest


class TestJsonRpcRequestParsing:
    def test_basic_request_parses_method(self) -> None:
        req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert req.method == "tools/list"

    def test_basic_request_parses_id(self) -> None:
        req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 42, "method": "ping"})
        assert req.id == 42

    def test_string_id_is_preserved(self) -> None:
        req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": "abc", "method": "ping"})
        assert req.id == "abc"

    def test_params_parsed_when_present(self) -> None:
        req = JsonRpcRequest.from_dict({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "shell", "arguments": {"command": "ls"}},
        })
        assert req.params is not None
        assert req.params["name"] == "shell"

    def test_params_none_when_absent(self) -> None:
        req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert req.params is None

    def test_notification_has_no_id(self) -> None:
        req = JsonRpcRequest.from_dict({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        assert req.id is None

    def test_notification_is_notification_property(self) -> None:
        req = JsonRpcRequest.from_dict({
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        })
        assert req.is_notification is True

    def test_non_notification_is_not_notification(self) -> None:
        req = JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 1, "method": "ping"})
        assert req.is_notification is False

    def test_missing_method_raises_value_error(self) -> None:
        with pytest.raises((ValueError, KeyError)):
            JsonRpcRequest.from_dict({"jsonrpc": "2.0", "id": 1})

    def test_to_dict_round_trips_request(self) -> None:
        req = JsonRpcRequest(method="tools/list", id=1, params={"cursor": None})
        d = req.to_dict()
        assert d["method"] == "tools/list"
        assert d["id"] == 1
        assert d["jsonrpc"] == "2.0"
