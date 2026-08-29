"""Tests for the /ws/terminal WebSocket endpoint."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from neuralcleave.gateway.origin_check import set_allowed_origins
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


class TestTerminalWSOriginCheck:
    """Round 6 gap analysis 5.2 (2026-08-29): this endpoint had no
    authentication of any kind - any web page open in the user's browser
    could connect and run arbitrary commands. CORSMiddleware never applies
    to WebSocket scope, so this handshake-level check is the only real
    protection."""

    def test_matching_origin_is_accepted(self):
        from neuralcleave.config import NeuralCleaveConfig

        set_allowed_origins(NeuralCleaveConfig())
        with TestClient(_app()) as client:
            with client.websocket_connect(
                "/ws/terminal", headers={"origin": "tauri://localhost"}
            ) as ws:
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"

    def test_mismatched_origin_is_rejected(self):
        from starlette.websockets import WebSocketDisconnect

        from neuralcleave.config import NeuralCleaveConfig

        set_allowed_origins(NeuralCleaveConfig())
        with TestClient(_app()) as client:
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect(
                    "/ws/terminal", headers={"origin": "https://evil.example.com"}
                ) as ws:
                    ws.receive_text()

    def test_missing_origin_is_still_accepted(self):
        """Preserves existing behavior for non-browser local test clients -
        a real browser always sends Origin for a cross-origin WebSocket
        handshake, so this doesn't weaken the actual protection."""
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                msg = json.loads(ws.receive_text())
                assert msg["type"] == "ready"

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
# WebSocket: env sanitization (round 6 gap analysis 5.2, 2026-08-29)
# ---------------------------------------------------------------------------


class TestTerminalWSEnvSanitization:
    """_run_command() previously passed the full, unsanitized process
    environment (env={**os.environ}) to every command - every configured
    provider API key was present in the subprocess environment, unlike
    ShellTool/BrowserAutomationTool which were already fixed in PR #142."""

    def test_sensitive_env_var_is_not_visible_to_the_command(self, monkeypatch):
        monkeypatch.setenv("FAKE_SECRET_API_KEY", "sk-should-not-leak-12345")
        cmd = (
            'python -c "import os; '
            "print(os.environ.get('FAKE_SECRET_API_KEY', 'ABSENT'))\""
        )
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": cmd}))
                output = ""
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "output":
                        output += msg["data"]
                    if msg["type"] == "exit":
                        break
                assert "sk-should-not-leak-12345" not in output
                assert "ABSENT" in output

    def test_non_sensitive_env_var_still_passes_through(self, monkeypatch):
        """Sanity check that the fix scrubs secrets specifically, not the
        whole environment (PATH, etc. must still work)."""
        monkeypatch.setenv("NEURALCLEAVE_TEST_HARMLESS_VAR", "visible-value")
        cmd = (
            'python -c "import os; '
            "print(os.environ.get('NEURALCLEAVE_TEST_HARMLESS_VAR', 'ABSENT'))\""
        )
        with TestClient(_app()) as client:
            with client.websocket_connect("/ws/terminal") as ws:
                ws.receive_text()  # ready
                ws.send_text(json.dumps({"type": "run", "cmd": cmd}))
                output = ""
                for _ in range(20):
                    msg = json.loads(ws.receive_text())
                    if msg["type"] == "output":
                        output += msg["data"]
                    if msg["type"] == "exit":
                        break
                assert "visible-value" in output


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


# ---------------------------------------------------------------------------
# Canvas CLI subcommands — _maybe_dispatch_nc unit tests
# ---------------------------------------------------------------------------


class TestCanvasCliDispatch:
    """Verify canvas subcommands are recognised and routed correctly.

    We mock _call_internal and the httpx client so no real HTTP request is
    made — we only assert the right routing decisions are taken.
    """

    def _make_nc_cmd_ws(self) -> tuple[TestClient, object]:
        return TestClient(_app())

    @pytest.mark.asyncio
    async def test_canvas_status_in_cmd_map(self):
        from neuralcleave.gateway.terminal import _NC_CMD_MAP

        assert ("canvas", "status") in _NC_CMD_MAP
        assert _NC_CMD_MAP[("canvas", "status")] == ("GET", "/api/v1/canvas/status")

    @pytest.mark.asyncio
    async def test_canvas_state_in_cmd_map(self):
        from neuralcleave.gateway.terminal import _NC_CMD_MAP

        assert ("canvas", "state") in _NC_CMD_MAP
        assert _NC_CMD_MAP[("canvas", "state")] == ("GET", "/api/v1/canvas/state")

    def test_canvas_command_in_help_text(self):
        from neuralcleave.gateway.terminal import _NC_HELP

        assert "canvas" in _NC_HELP
        assert "canvas render" in _NC_HELP
        assert "canvas clear" in _NC_HELP

    @pytest.mark.asyncio
    async def test_canvas_clear_dispatched(self):
        """neuralcleave canvas clear → DELETE /api/v1/canvas/clear."""
        from neuralcleave.gateway.terminal import _maybe_dispatch_nc

        calls: list[tuple] = []

        async def fake_call(ws, method, path, params=None):
            calls.append((method, path))

        ws = MagicMock()
        ws.send_text = AsyncMock()
        with patch("neuralcleave.gateway.terminal._call_internal", new=fake_call):
            result = await _maybe_dispatch_nc(ws, "neuralcleave canvas clear")
        assert result is True
        assert calls == [("DELETE", "/api/v1/canvas/clear")]

    @pytest.mark.asyncio
    async def test_canvas_render_text_posts_correctly(self):
        """neuralcleave canvas render --text 'Hello' → POST /api/v1/canvas/render."""
        from neuralcleave.gateway.terminal import _maybe_dispatch_nc

        posted: list[dict] = []

        class FakeResponse:
            status_code = 201
            headers = {"content-type": "application/json"}

            def json(self):
                return {"id": "abc", "block_type": "text"}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def post(self, path, json=None):
                posted.append({"path": path, "body": json})
                return FakeResponse()

        ws = MagicMock()
        ws.send_text = AsyncMock()
        with patch("neuralcleave.gateway.terminal.httpx.AsyncClient", return_value=FakeClient()):
            result = await _maybe_dispatch_nc(ws, "neuralcleave canvas render --text Hello World")
        assert result is True
        assert posted[0]["body"]["block_type"] == "text"
        assert "Hello" in posted[0]["body"]["content"]

    @pytest.mark.asyncio
    async def test_canvas_render_markdown_flag(self):
        from neuralcleave.gateway.terminal import _maybe_dispatch_nc

        posted: list[dict] = []

        class FakeResponse:
            status_code = 201
            headers = {"content-type": "application/json"}

            def json(self):
                return {}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def post(self, path, json=None):
                posted.append(json)
                return FakeResponse()

        ws = MagicMock()
        ws.send_text = AsyncMock()
        with patch("neuralcleave.gateway.terminal.httpx.AsyncClient", return_value=FakeClient()):
            await _maybe_dispatch_nc(ws, "neuralcleave canvas render --markdown # Hello")
        assert posted[0]["block_type"] == "markdown"

    @pytest.mark.asyncio
    async def test_canvas_render_with_title(self):
        from neuralcleave.gateway.terminal import _maybe_dispatch_nc

        posted: list[dict] = []

        class FakeResponse:
            status_code = 201
            headers = {"content-type": "application/json"}

            def json(self):
                return {}

        class FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def post(self, path, json=None):
                posted.append(json)
                return FakeResponse()

        ws = MagicMock()
        ws.send_text = AsyncMock()
        with patch("neuralcleave.gateway.terminal.httpx.AsyncClient", return_value=FakeClient()):
            await _maybe_dispatch_nc(ws, "neuralcleave canvas render --text Hello --title MyTitle")
        assert posted[0]["title"] == "MyTitle"
        assert posted[0]["content"] == "Hello"
