"""Unit tests for NeuralCleave.channels.signal_ — SignalAdapter."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from neuralcleave.channels.signal_ import SignalAdapter


def make_adapter(**overrides) -> SignalAdapter:
    cfg = {"phone_number": "+14155551234", "cli_path": "/usr/bin/signal-cli", **overrides}
    return SignalAdapter(cfg)


async def _async_lines(lines: list[bytes]):
    for line in lines:
        yield line


# ---------------------------------------------------------------------------
# Construction / resolution
# ---------------------------------------------------------------------------


def test_channel_id():
    assert make_adapter().channel_id == "signal"


def test_defaults():
    adapter = SignalAdapter({})
    assert adapter._phone == ""
    assert adapter._cli_path == "signal-cli"
    assert adapter._data_path == ""


def test_resolve_env(monkeypatch):
    monkeypatch.setenv("SIGNAL_CLI_TEST_PATH", "/custom/signal-cli")
    adapter = make_adapter(cli_path="ENV:SIGNAL_CLI_TEST_PATH")
    assert adapter._cli_path == "/custom/signal-cli"


def test_config_schema_required_fields():
    schema = make_adapter().get_config_schema()
    assert schema["required"] == ["phone_number"]


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_connect_binary_not_found_raises():
    adapter = make_adapter()
    with patch("asyncio.create_subprocess_exec", AsyncMock(side_effect=FileNotFoundError())):
        with pytest.raises(RuntimeError, match="signal-cli not found"):
            await adapter.connect()


@pytest.mark.asyncio
async def test_connect_success_starts_process_and_read_task():
    adapter = make_adapter(data_path="~/.local/share/signal-cli")
    mock_process = MagicMock()
    mock_process.stdout = None  # _read_loop exits immediately

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_process)) as create_mock:
        await adapter.connect()
        await asyncio.sleep(0)

    assert adapter._process is mock_process
    assert adapter._read_task is not None
    cmd = create_mock.call_args[0]
    assert "--data-path" in cmd
    assert "-a" in cmd
    assert "+14155551234" in cmd

    await adapter.disconnect()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_disconnect_with_no_process_or_task_is_noop():
    adapter = make_adapter()
    await adapter.disconnect()  # should not raise


@pytest.mark.asyncio
async def test_disconnect_terminates_process_cleanly():
    adapter = make_adapter()
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock()
    adapter._process = mock_process

    async def _never_ending():
        await asyncio.sleep(100)

    adapter._read_task = asyncio.create_task(_never_ending())

    await adapter.disconnect()

    assert adapter._process is None
    assert adapter._read_task is None
    mock_process.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_kills_process_if_terminate_times_out():
    adapter = make_adapter()
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_process.kill = MagicMock()
    adapter._process = mock_process

    await adapter.disconnect()

    mock_process.kill.assert_called_once()
    assert adapter._process is None


@pytest.mark.asyncio
async def test_disconnect_swallows_kill_failure_too():
    adapter = make_adapter()
    mock_process = MagicMock()
    mock_process.terminate = MagicMock()
    mock_process.wait = AsyncMock(side_effect=asyncio.TimeoutError())
    mock_process.kill = MagicMock(side_effect=Exception("already dead"))
    adapter._process = mock_process

    await adapter.disconnect()  # should not raise even though kill() also fails

    assert adapter._process is None


# ---------------------------------------------------------------------------
# send()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_send_no_process_returns_none():
    adapter = make_adapter()
    result = await adapter.send("+15551234567", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_success_returns_rpc_id():
    adapter = make_adapter()
    adapter._process = MagicMock()
    adapter._process.stdin = MagicMock()
    adapter._process.stdin.write = MagicMock()
    adapter._process.stdin.drain = AsyncMock()

    result = await adapter.send("+15551234567", "hello")

    assert result is not None
    assert result.startswith("send-")
    adapter._process.stdin.write.assert_called_once()


@pytest.mark.asyncio
async def test_send_no_stdin_returns_none():
    adapter = make_adapter()
    adapter._process = MagicMock()
    adapter._process.stdin = None
    result = await adapter.send("+15551234567", "hello")
    assert result is None


@pytest.mark.asyncio
async def test_send_write_exception_returns_none():
    adapter = make_adapter()
    adapter._process = MagicMock()
    adapter._process.stdin = MagicMock()
    adapter._process.stdin.write = MagicMock(side_effect=Exception("broken pipe"))

    result = await adapter.send("+15551234567", "hello")

    assert result is None


# ---------------------------------------------------------------------------
# _read_loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_loop_no_process_returns_immediately():
    adapter = make_adapter()
    await adapter._read_loop()  # no process set


@pytest.mark.asyncio
async def test_read_loop_no_stdout_returns_immediately():
    adapter = make_adapter()
    adapter._process = MagicMock()
    adapter._process.stdout = None
    await adapter._read_loop()


@pytest.mark.asyncio
async def test_read_loop_processes_valid_json_line():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    notification = {
        "method": "receive",
        "params": {"envelope": {"source": "+1555", "dataMessage": {"message": "hi"}}},
    }
    adapter._process = MagicMock()
    adapter._process.stdout = _async_lines([(json.dumps(notification) + "\n").encode()])

    await adapter._read_loop()
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].text == "hi"


@pytest.mark.asyncio
async def test_read_loop_skips_non_json_lines():
    adapter = make_adapter()
    adapter._process = MagicMock()
    adapter._process.stdout = _async_lines([b"not valid json\n", b"\n"])

    await adapter._read_loop()  # should not raise


@pytest.mark.asyncio
async def test_read_loop_handles_cancelled_error():
    adapter = make_adapter()
    adapter._process = MagicMock()

    async def _raise_cancelled():
        raise asyncio.CancelledError()
        yield  # pragma: no cover - unreachable, makes this an async generator

    adapter._process.stdout = _raise_cancelled()

    await adapter._read_loop()  # should swallow CancelledError


@pytest.mark.asyncio
async def test_read_loop_handles_generic_exception():
    adapter = make_adapter()
    adapter._process = MagicMock()

    async def _raise_generic():
        raise RuntimeError("stdout broke")
        yield  # pragma: no cover - unreachable, makes this an async generator

    adapter._process.stdout = _raise_generic()

    await adapter._read_loop()  # should swallow and log, not raise


# ---------------------------------------------------------------------------
# _process_event
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_process_event_ignores_non_receive_method():
    adapter = make_adapter()
    dispatched = []
    adapter.on_message(lambda msg: dispatched.append(msg))

    await adapter._process_event({"method": "send", "params": {}})

    assert dispatched == []


@pytest.mark.asyncio
async def test_process_event_ignores_empty_message():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    await adapter._process_event({
        "method": "receive",
        "params": {"envelope": {"source": "+1555", "dataMessage": {"message": ""}}},
    })
    await asyncio.sleep(0)

    assert dispatched == []


@pytest.mark.asyncio
async def test_process_event_dispatches_with_attachments_and_group():
    adapter = make_adapter()
    dispatched = []

    async def handler(msg):
        dispatched.append(msg)

    adapter.on_message(handler)

    await adapter._process_event({
        "method": "receive",
        "params": {
            "envelope": {
                "source": "+1555",
                "sourceName": "Alice",
                "dataMessage": {
                    "message": "hello group",
                    "groupInfo": {"groupId": "group-abc"},
                    "attachments": [{"filename": "pic.jpg", "contentType": "image/jpeg"}],
                },
            }
        },
    })
    await asyncio.sleep(0)

    assert len(dispatched) == 1
    assert dispatched[0].sender_name == "Alice"
    assert dispatched[0].thread_id == "group-abc"
    assert len(dispatched[0].attachments) == 1
    assert dispatched[0].attachments[0].filename == "pic.jpg"


@pytest.mark.asyncio
async def test_process_event_no_handler_does_not_raise():
    adapter = make_adapter()
    await adapter._process_event({
        "method": "receive",
        "params": {"envelope": {"source": "+1555", "dataMessage": {"message": "hi"}}},
    })
