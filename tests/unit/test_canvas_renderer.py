"""Unit tests for cortexflow_ai.canvas.renderer — CanvasRenderer."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from cortexflow_ai.canvas.block import CanvasBlock
from cortexflow_ai.canvas.renderer import MAX_BLOCKS, CanvasRenderer


def make_block(bt: str = "text", content: str = "hello") -> CanvasBlock:
    return CanvasBlock.new(bt, content)


@pytest.fixture()
def renderer():
    return CanvasRenderer()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


def test_initial_block_count(renderer):
    assert renderer.block_count() == 0


def test_initial_subscriber_count(renderer):
    assert renderer.subscriber_count() == 0


def test_initial_get_state(renderer):
    state = renderer.get_state()
    assert state["blocks"] == []
    assert state["count"] == 0


# ---------------------------------------------------------------------------
# add_block
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_add_block_increments_count(renderer):
    await renderer.add_block(make_block())
    assert renderer.block_count() == 1


@pytest.mark.asyncio
async def test_add_block_updates_state(renderer):
    b = make_block("markdown", "**hi**")
    await renderer.add_block(b)
    state = renderer.get_state()
    assert state["count"] == 1
    assert state["blocks"][0]["id"] == b.id


@pytest.mark.asyncio
async def test_add_multiple_blocks(renderer):
    for _ in range(5):
        await renderer.add_block(make_block())
    assert renderer.block_count() == 5


@pytest.mark.asyncio
async def test_add_block_broadcasts_to_subscriber(renderer):
    ws = AsyncMock()
    await renderer.subscribe(ws)
    ws.send_text.reset_mock()

    b = make_block("text", "broadcast")
    await renderer.add_block(b)

    ws.send_text.assert_awaited_once()
    msg = json.loads(ws.send_text.call_args[0][0])
    assert msg["type"] == "add"
    assert msg["block"]["id"] == b.id


@pytest.mark.asyncio
async def test_add_block_no_subscribers_no_error(renderer):
    await renderer.add_block(make_block())  # should not raise


# ---------------------------------------------------------------------------
# MAX_BLOCKS cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_max_blocks_cap(renderer):
    for i in range(MAX_BLOCKS + 10):
        await renderer.add_block(make_block("text", f"block {i}"))
    assert renderer.block_count() == MAX_BLOCKS


@pytest.mark.asyncio
async def test_max_blocks_keeps_newest(renderer):
    for i in range(MAX_BLOCKS + 5):
        await renderer.add_block(make_block("text", f"block {i}"))
    state = renderer.get_state()
    last = state["blocks"][-1]["content"]
    assert last == f"block {MAX_BLOCKS + 4}"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_clear_empties_blocks(renderer):
    await renderer.add_block(make_block())
    await renderer.add_block(make_block())
    await renderer.clear()
    assert renderer.block_count() == 0


@pytest.mark.asyncio
async def test_clear_broadcasts_clear_message(renderer):
    ws = AsyncMock()
    await renderer.subscribe(ws)
    ws.send_text.reset_mock()

    await renderer.clear()

    ws.send_text.assert_awaited()
    last_call = ws.send_text.call_args_list[-1][0][0]
    msg = json.loads(last_call)
    assert msg["type"] == "clear"


@pytest.mark.asyncio
async def test_clear_empty_canvas_no_error(renderer):
    await renderer.clear()  # should not raise


# ---------------------------------------------------------------------------
# subscribe / unsubscribe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_subscribe_increments_count(renderer):
    ws = AsyncMock()
    await renderer.subscribe(ws)
    assert renderer.subscriber_count() == 1


@pytest.mark.asyncio
async def test_subscribe_sends_current_state(renderer):
    await renderer.add_block(make_block("text", "existing"))
    ws = AsyncMock()
    await renderer.subscribe(ws)
    msg = json.loads(ws.send_text.call_args[0][0])
    assert msg["type"] == "state"
    assert len(msg["blocks"]) == 1


@pytest.mark.asyncio
async def test_subscribe_empty_canvas_sends_state(renderer):
    ws = AsyncMock()
    await renderer.subscribe(ws)
    msg = json.loads(ws.send_text.call_args[0][0])
    assert msg["type"] == "state"
    assert msg["blocks"] == []


@pytest.mark.asyncio
async def test_subscribe_failed_send_removes_subscriber(renderer):
    ws = AsyncMock()
    ws.send_text.side_effect = Exception("closed")
    await renderer.subscribe(ws)
    assert renderer.subscriber_count() == 0


def test_unsubscribe_decrements_count(renderer):
    ws = MagicMock()
    renderer._subscribers.append(ws)
    renderer.unsubscribe(ws)
    assert renderer.subscriber_count() == 0


def test_unsubscribe_nonexistent_no_error(renderer):
    renderer.unsubscribe(MagicMock())  # should not raise


@pytest.mark.asyncio
async def test_multiple_subscribers_all_receive(renderer):
    ws1, ws2 = AsyncMock(), AsyncMock()
    await renderer.subscribe(ws1)
    await renderer.subscribe(ws2)
    ws1.send_text.reset_mock()
    ws2.send_text.reset_mock()

    await renderer.add_block(make_block("text", "multi"))

    ws1.send_text.assert_awaited_once()
    ws2.send_text.assert_awaited_once()


# ---------------------------------------------------------------------------
# Dead subscriber cleanup during broadcast
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dead_subscriber_removed_during_broadcast(renderer):
    ws_dead = AsyncMock()
    ws_alive = AsyncMock()
    await renderer.subscribe(ws_dead)
    await renderer.subscribe(ws_alive)
    ws_dead.send_text.reset_mock()
    ws_alive.send_text.reset_mock()
    ws_dead.send_text.side_effect = Exception("broken pipe")

    await renderer.add_block(make_block())

    assert renderer.subscriber_count() == 1
    ws_alive.send_text.assert_awaited_once()
