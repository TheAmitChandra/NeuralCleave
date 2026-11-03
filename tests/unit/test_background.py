"""Tests for neuralcleave.background.spawn_background."""

from __future__ import annotations

import asyncio
import gc

from neuralcleave import background


async def test_task_is_referenced_until_done():
    gate = asyncio.Event()
    ran = []

    async def work():
        await gate.wait()
        ran.append(True)

    task = background.spawn_background(work())
    assert task in background._background_tasks
    gc.collect()
    gate.set()
    await task
    await asyncio.sleep(0)
    assert ran == [True]
    assert task not in background._background_tasks


async def test_exception_is_logged_and_released(caplog):
    async def boom():
        raise RuntimeError("kaput")

    with caplog.at_level("ERROR", logger="neuralcleave.background"):
        task = background.spawn_background(boom(), name="boom")
        await asyncio.wait([task])
        await asyncio.sleep(0)

    assert task not in background._background_tasks
    assert "boom" in caplog.text and "kaput" in caplog.text


async def test_cancelled_task_is_released():
    async def forever():
        await asyncio.sleep(60)

    task = background.spawn_background(forever())
    task.cancel()
    await asyncio.wait([task])
    await asyncio.sleep(0)
    assert task not in background._background_tasks


async def test_explicit_loop():
    async def noop():
        return 1

    task = background.spawn_background(noop(), loop=asyncio.get_running_loop())
    assert await task == 1
