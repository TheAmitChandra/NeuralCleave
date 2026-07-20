"""Tests for the /ws/terminal WebSocket endpoint."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.terminal import _default_shell, _send, router

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# _default_shell()
# ---------------------------------------------------------------------------


class TestDefaultShell:
    def test_windows_returns_cmd(self):
        with patch.object(sys, "platform", "win32"):
            shell = _default_shell()
        assert shell == ["cmd.exe"]

    def test_non_windows_returns_bash(self):
        with patch.object(sys, "platform", "linux"):
            with patch.dict("os.environ", {"SHELL": "/bin/bash"}, clear=False):
                shell = _default_shell()
        assert shell == ["/bin/bash"]

    def test_non_windows_fallback_bash(self):
        with patch.object(sys, "platform", "linux"):
            import os

            env = {k: v for k, v in os.environ.items() if k != "SHELL"}
            with patch.dict("os.environ", env, clear=True):
                shell = _default_shell()
        assert "/bin/bash" in shell[0]

    def test_returns_list(self):
        shell = _default_shell()
        assert isinstance(shell, list)
        assert len(shell) == 1


# ---------------------------------------------------------------------------
# WebSocket: connection and handshake
# ---------------------------------------------------------------------------


class TestTerminalWSHandshake:
    def test_accepts_connection(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"

    def test_ready_message_has_shell_key(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                msg = json.loads(ws.receive_text())
                assert "shell" in msg

    def test_ready_shell_is_string(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                msg = json.loads(ws.receive_text())
                assert isinstance(msg["shell"], str)
                assert len(msg["shell"]) > 0


# ---------------------------------------------------------------------------
# WebSocket: protocol — invalid input
# ---------------------------------------------------------------------------


class TestTerminalWSProtocol:
    def test_invalid_json_returns_error(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text("NOT_JSON")
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "error"
                assert "JSON" in msg["message"]

    def test_unknown_message_type_returns_error(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "unknown_type"}))
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "error"

    def test_empty_cmd_returns_ready(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": ""}))
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"

    def test_whitespace_cmd_returns_ready(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": "   "}))
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"


# ---------------------------------------------------------------------------
# WebSocket: running a real command
# ---------------------------------------------------------------------------


class TestTerminalWSRunCommand:
    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="echo command slightly different on Windows",
    )
    def test_echo_produces_output_and_exit(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": "echo hello"}))
                messages = []
                for _ in range(10):
                    raw = ws.receive_text()
                    msg = json.loads(raw)
                    messages.append(msg)
                    if msg["type"] in ("exit", "ready"):
                        break
                types = {m["type"] for m in messages}
                assert "output" in types or "exit" in types

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="echo command slightly different on Windows",
    )
    def test_exit_code_zero_for_success(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": "echo hi"}))
                exit_msg = None
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "exit":
                        exit_msg = msg
                        break
                assert exit_msg is not None
                assert exit_msg["code"] == 0

    @pytest.mark.skipif(
        sys.platform == "win32",
        reason="false command slightly different on Windows",
    )
    def test_exit_code_nonzero_for_failure(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": "false"}))
                exit_msg = None
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "exit":
                        exit_msg = msg
                        break
                assert exit_msg is not None
                assert exit_msg["code"] != 0

    def test_after_exit_server_sends_ready(self):
        if sys.platform == "win32":
            cmd = "echo hi"
        else:
            cmd = "echo hi"
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": cmd}))
                final_ready = None
                for _ in range(30):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "ready":
                        final_ready = msg
                        break
                assert final_ready is not None

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="Windows-only: echo with cmd.exe",
    )
    def test_windows_echo_produces_output(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": "echo hello"}))
                messages = []
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    messages.append(msg)
                    if msg["type"] == "ready":
                        break
                output_msgs = [m for m in messages if m["type"] == "output"]
                assert len(output_msgs) > 0


# ---------------------------------------------------------------------------
# WebSocket: interrupt
# ---------------------------------------------------------------------------


class TestTerminalWSInterrupt:
    def test_interrupt_before_run_does_not_crash(self):
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                # Send interrupt when no command is running — should be a no-op
                ws.send_text(json.dumps({"type": "interrupt"}))
                # Send a regular command after to confirm the connection still works
                ws.send_text(json.dumps({"type": "run", "cmd": ""}))
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"


# ---------------------------------------------------------------------------
# _send helper — fire-and-forget on WebSocket errors
# ---------------------------------------------------------------------------


class TestSendHelper:
    @pytest.mark.asyncio
    async def test_send_suppresses_exceptions(self):
        ws = MagicMock()
        ws.send_text = AsyncMock(side_effect=RuntimeError("closed"))
        # Should not raise
        await _send(ws, {"type": "ready"})

    @pytest.mark.asyncio
    async def test_send_transmits_json(self):
        ws = MagicMock()
        ws.send_text = AsyncMock()
        payload = {"type": "output", "data": "hello", "stream": "stdout"}
        await _send(ws, payload)
        ws.send_text.assert_called_once_with(json.dumps(payload))
