"""Verify routed tasks exercise real pipeline behavior, not only node selection."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from neuralcleave.agent.pipeline import CognitivePipeline
from neuralcleave.agent.session import Session
from neuralcleave.channels.base import InboundMessage
from neuralcleave.models.router import GenerationResult
from neuralcleave.orchestrator.execution import PipelineExecutor
from neuralcleave.orchestrator.node import AgentNodeConfig
from neuralcleave.orchestrator.orchestrator import AgentOrchestrator
from neuralcleave.orchestrator.task import AgentTask
from neuralcleave.tools.base import ToolResult
from neuralcleave.workspace import WorkspaceFiles


def make_pipeline():
    router = MagicMock()
    router.generate = AsyncMock(return_value=GenerationResult(text="answer", model="test", provider="fake"))
    memory = MagicMock()
    memory.retrieve = AsyncMock(return_value=SimpleNamespace(to_prompt_blocks=lambda: [], token_estimate=0))
    memory.store_short_term = AsyncMock()
    reflection = SimpleNamespace(reflect=AsyncMock(return_value=SimpleNamespace(final_response="reviewed", score=91)))
    tools = MagicMock()
    tools.names = ["lookup"]
    tools.tools_prompt_block.return_value = "lookup: find a fact"
    tools.call = AsyncMock(return_value=ToolResult(tool="lookup", output="verified fact"))
    pipeline = CognitivePipeline(router, memory, WorkspaceFiles(), reflection=reflection, tool_registry=tools)
    return pipeline, router, reflection, tools


async def test_routed_task_runs_tools_reflection_and_node_memory():
    pipeline, router, reflection, tools = make_pipeline()
    router.generate.side_effect = [
        GenerationResult(text='TOOL_CALL: {"name":"lookup","arguments":{}}', model="chosen", provider="fake"),
        GenerationResult(text="raw answer", model="chosen", provider="fake"),
    ]
    orch = AgentOrchestrator(router=router, executor=PipelineExecutor(pipeline))
    orch.register(AgentNodeConfig(name="research", model_override="chosen"))
    orch.memory_for_node("research").put("fact", "remember this fact")
    result = await orch.route(AgentTask("hi", session_id="owner", task_type="research", source_channel="web"))
    assert result.content == "reviewed"
    assert result.metadata["tool_steps"] == 1
    assert result.metadata["quality_score"] == 91
    assert tools.call.await_count == 1
    assert reflection.reflect.await_count == 1
    for call in router.generate.await_args_list:
        assert call.kwargs["model_override"] == "chosen"
        assert call.kwargs["channel_id"] == "web"
        assert call.kwargs["task_type"] == "research"
        assert "remember this fact" in call.kwargs["system"]
    assert orch.memory_for_node("research").count() == 2
    pipeline._memory.retrieve.assert_not_awaited()


async def test_namespaces_do_not_leak_and_clear_removes_future_context():
    pipeline, router, _, _ = make_pipeline()
    orch = AgentOrchestrator(executor=PipelineExecutor(pipeline))
    orch.register(AgentNodeConfig(name="one", task_types=["one"]))
    orch.register(AgentNodeConfig(name="two", task_types=["two"]))
    orch.memory_for_node("one").put("private", "only-node-one")
    await orch.route(AgentTask("hi", task_type="two"))
    assert "only-node-one" not in router.generate.await_args.kwargs["system"]
    await orch.route(AgentTask("hi", task_type="one"))
    assert "only-node-one" in router.generate.await_args.kwargs["system"]
    orch.memory_for_node("one").clear()
    await orch.route(AgentTask("hi", task_type="one"))
    assert "only-node-one" not in router.generate.await_args.kwargs["system"]


async def test_executor_failure_is_sanitized_and_timeout_is_enforced():
    async def slow(*args):
        await asyncio.sleep(60)
    orch = AgentOrchestrator(executor=slow)
    orch.register(AgentNodeConfig(name="slow"))
    result = await orch.route(AgentTask("hi", timeout=0.01))
    assert result.metadata["error"] == "Agent execution failed"


async def test_pipeline_serializes_same_session_and_drains_writes():
    pipeline, router, _, _ = make_pipeline()
    session = Session("web", "owner")
    entered = asyncio.Event()
    release = asyncio.Event()

    async def generate(prompt, **kwargs):
        entered.set()
        await release.wait()
        return GenerationResult(text="reply", model="test", provider="fake")

    router.generate.side_effect = generate
    message = InboundMessage(channel="web", sender_id="owner", sender_name="Owner", text="hi")
    first = asyncio.create_task(pipeline.run(message, session))
    await entered.wait()
    second = asyncio.create_task(pipeline.run(message, session))
    await asyncio.sleep(0)
    assert router.generate.await_count == 1
    release.set()
    await asyncio.gather(first, second)
    await pipeline.drain()
    assert pipeline._memory.store_short_term.await_count == 2
    assert session.turn_count == 4
    assert not pipeline._pending
    assert router.generate.await_args.kwargs["channel_id"] == "web"


@pytest.mark.parametrize("streaming", [False, True])
async def test_channel_is_forwarded_for_generation(streaming):
    from neuralcleave.models.router import StreamChunk

    pipeline, router, _, _ = make_pipeline()
    seen = []
    async def stream(prompt, **kwargs):
        seen.append(kwargs)
        yield StreamChunk(text="hello")
        yield StreamChunk(done=True, model="test", provider="fake")
    router.generate_stream = stream
    message = InboundMessage(channel="telegram", sender_id="1", sender_name="Owner", text="hi")
    if streaming:
        chunks = [c async for c in pipeline.run_stream(message, Session("telegram", "1"))]
        assert chunks[-1].result.response == "hello"
        assert seen[0]["channel_id"] == "telegram"
    else:
        await pipeline.run(message, Session("telegram", "1"))
        assert router.generate.await_args.kwargs["channel_id"] == "telegram"
    await pipeline.drain()
