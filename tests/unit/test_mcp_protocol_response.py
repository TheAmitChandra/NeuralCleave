"""Tests for JsonRpcResponse and JsonRpcError serialisation."""

from __future__ import annotations

from neuralcleave.mcp.protocol import JsonRpcError, JsonRpcResponse


class TestJsonRpcResponse:
    def test_ok_response_has_result_key(self) -> None:
        resp = JsonRpcResponse.ok(1, {"tools": []})
        d = resp.to_dict()
        assert "result" in d
        assert "error" not in d

    def test_ok_response_result_matches_payload(self) -> None:
        resp = JsonRpcResponse.ok(2, {"count": 3})
        assert resp.to_dict()["result"] == {"count": 3}

    def test_ok_response_id_preserved(self) -> None:
        resp = JsonRpcResponse.ok(99, {})
        assert resp.to_dict()["id"] == 99

    def test_ok_response_includes_jsonrpc_version(self) -> None:
        resp = JsonRpcResponse.ok(1, {})
        assert resp.to_dict()["jsonrpc"] == "2.0"

    def test_error_response_has_error_key(self) -> None:
        resp = JsonRpcResponse.err(1, -32601, "Method not found")
        d = resp.to_dict()
        assert "error" in d
        assert "result" not in d

    def test_error_response_code_and_message(self) -> None:
        resp = JsonRpcResponse.err(1, -32700, "Parse error")
        err = resp.to_dict()["error"]
        assert err["code"] == -32700
        assert err["message"] == "Parse error"

    def test_error_response_null_id_preserved(self) -> None:
        resp = JsonRpcResponse.err(None, -32700, "Parse error")
        assert resp.to_dict()["id"] is None

    def test_json_rpc_error_with_data(self) -> None:
        err = JsonRpcError(code=-32602, message="Invalid params", data={"field": "name"})
        d = err.to_dict()
        assert d["data"] == {"field": "name"}

    def test_json_rpc_error_without_data_omits_key(self) -> None:
        err = JsonRpcError(code=-32601, message="Method not found")
        d = err.to_dict()
        assert "data" not in d
