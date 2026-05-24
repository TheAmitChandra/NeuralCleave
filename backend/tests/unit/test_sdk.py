"""Unit tests for the CortexFlow Plugin & SDK.

Tests cover:
- ToolSDK base class registration and execution
- @sdk_tool decorator (happy path + error cases)
- register_tool() functional helper
- AgentSDK lifecycle hooks (on_start, on_stop, on_error)
- AgentSDK.dispatch() wrapping (success + exception path)
- AgentSDK.call_tool() delegation to ToolRegistry
- AgentRegistry (register, get, list_types, unregister, duplicate guard)
- SDK __init__ re-exports
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_registry():
    """Return a fresh ToolRegistry instance (not the global singleton)."""
    from app.core.tools.registry import ToolRegistry
    reg = ToolRegistry()
    return reg


# ---------------------------------------------------------------------------
# ToolSDK — base class
# ---------------------------------------------------------------------------


class TestToolSDKBaseClass:
    def test_register_adds_tool_to_registry(self):
        from app.sdk.tool_sdk import ToolSDK

        class PingTool(ToolSDK):
            name = "ping"
            description = "Returns pong"
            permissions = []
            risk_level = "low"

            async def run(self, parameters: dict) -> dict:
                return {"pong": True}

        reg = _fresh_registry()
        tool = PingTool()
        tool.register(registry=reg)

        assert "ping" in reg._tools
        assert reg._tools["ping"].risk_level == "low"
        assert "ping" in reg._handlers

    def test_register_raises_if_name_empty(self):
        from app.sdk.tool_sdk import ToolSDK

        class BadTool(ToolSDK):
            name = ""  # missing name
            description = "No name"
            permissions = []
            risk_level = "low"

            async def run(self, parameters: dict) -> dict:
                return {}

        with pytest.raises(ValueError, match="name must be set"):
            BadTool().register(registry=_fresh_registry())

    def test_build_definition_fields(self):
        from app.sdk.tool_sdk import ToolSDK

        class DetailedTool(ToolSDK):
            name = "detailed_tool"
            description = "A detailed tool"
            permissions = ["file.read", "network.external"]
            risk_level = "medium"
            requires_approval = True
            sandbox_required = True
            timeout_seconds = 60
            parameters_schema = {"type": "object"}

            async def run(self, parameters: dict) -> dict:
                return {}

        defn = DetailedTool()._build_definition()

        assert defn.name == "detailed_tool"
        assert defn.permissions == ["file.read", "network.external"]
        assert defn.risk_level == "medium"
        assert defn.requires_approval is True
        assert defn.sandbox_required is True
        assert defn.timeout_seconds == 60
        assert defn.parameters_schema == {"type": "object"}

    @pytest.mark.asyncio
    async def test_run_not_implemented_raises(self):
        from app.sdk.tool_sdk import ToolSDK

        class AbstractTool(ToolSDK):
            name = "abstract_tool"
            description = "Not implemented"
            permissions = []
            risk_level = "low"

        with pytest.raises(NotImplementedError):
            await AbstractTool().run({})


# ---------------------------------------------------------------------------
# @sdk_tool decorator
# ---------------------------------------------------------------------------


class TestSdkToolDecorator:
    def test_decorator_registers_coroutine(self):
        from app.sdk.tool_sdk import sdk_tool

        reg = _fresh_registry()

        @sdk_tool(
            name="echo_decorator",
            description="Echo test",
            permissions=[],
            risk_level="low",
            registry=reg,
        )
        async def echo_decorator(parameters: dict) -> dict:
            return parameters

        assert "echo_decorator" in reg._tools

    def test_decorator_rejects_sync_function(self):
        from app.sdk.tool_sdk import sdk_tool

        reg = _fresh_registry()

        with pytest.raises(TypeError, match="async function"):
            @sdk_tool(
                name="sync_tool",
                description="Bad",
                permissions=[],
                risk_level="low",
                registry=reg,
            )
            def sync_tool(parameters: dict) -> dict:  # not async
                return parameters

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_behaviour(self):
        from app.sdk.tool_sdk import sdk_tool

        reg = _fresh_registry()

        @sdk_tool(
            name="calculator",
            description="Adds two numbers",
            permissions=[],
            risk_level="low",
            registry=reg,
        )
        async def calculator(parameters: dict) -> dict:
            return {"result": parameters["a"] + parameters["b"]}

        # Call directly (bypasses registry pipeline)
        result = await calculator({"a": 3, "b": 4})
        assert result == {"result": 7}

    def test_decorator_preserves_function_name(self):
        from app.sdk.tool_sdk import sdk_tool

        reg = _fresh_registry()

        @sdk_tool(
            name="named_tool",
            description="Named",
            permissions=[],
            risk_level="low",
            registry=reg,
        )
        async def my_named_function(parameters: dict) -> dict:
            return {}

        assert my_named_function.__name__ == "my_named_function"

    def test_decorator_passes_schema(self):
        from app.sdk.tool_sdk import sdk_tool

        schema = {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }
        reg = _fresh_registry()

        @sdk_tool(
            name="search_tool",
            description="Search",
            permissions=["network.external"],
            risk_level="low",
            parameters_schema=schema,
            registry=reg,
        )
        async def search_tool(parameters: dict) -> dict:
            return {}

        assert reg._tools["search_tool"].parameters_schema == schema


# ---------------------------------------------------------------------------
# register_tool() functional helper
# ---------------------------------------------------------------------------


class TestRegisterTool:
    def test_registers_handler_directly(self):
        from app.sdk.tool_sdk import register_tool

        reg = _fresh_registry()

        async def my_handler(parameters: dict) -> dict:
            return {"ok": True}

        register_tool(
            my_handler,
            name="direct_tool",
            description="Direct",
            permissions=[],
            risk_level="low",
            registry=reg,
        )

        assert "direct_tool" in reg._tools
        assert reg._handlers["direct_tool"] is my_handler

    def test_accepts_all_optional_kwargs(self):
        from app.sdk.tool_sdk import register_tool

        reg = _fresh_registry()

        async def handler(p: dict) -> dict:
            return {}

        register_tool(
            handler,
            name="full_tool",
            description="Full",
            permissions=["file.write"],
            risk_level="high",
            requires_approval=True,
            sandbox_required=True,
            timeout_seconds=120,
            parameters_schema={"type": "object"},
            registry=reg,
        )

        defn = reg._tools["full_tool"]
        assert defn.requires_approval is True
        assert defn.sandbox_required is True
        assert defn.timeout_seconds == 120


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    def setup_method(self):
        """Ensure clean registry state between tests."""
        from app.sdk.agent_sdk import AgentRegistry
        # Unregister any leftover types from previous tests
        for name in list(AgentRegistry._registry.keys()):
            AgentRegistry.unregister(name)

    def test_register_and_get(self):
        from app.sdk.agent_sdk import AgentRegistry, AgentSDK

        class EchoAgent(AgentSDK):
            agent_type = "echo_agent"
            async def handle_task(self, task_payload: dict) -> dict:
                return task_payload

        AgentRegistry.register(EchoAgent)
        assert AgentRegistry.get("echo_agent") is EchoAgent

    def test_get_unknown_returns_none(self):
        from app.sdk.agent_sdk import AgentRegistry
        assert AgentRegistry.get("does_not_exist") is None

    def test_list_types(self):
        from app.sdk.agent_sdk import AgentRegistry, AgentSDK

        class TypeA(AgentSDK):
            agent_type = "type_a"
            async def handle_task(self, p: dict) -> dict: return {}

        class TypeB(AgentSDK):
            agent_type = "type_b"
            async def handle_task(self, p: dict) -> dict: return {}

        AgentRegistry.register(TypeA)
        AgentRegistry.register(TypeB)
        types = AgentRegistry.list_types()
        assert "type_a" in types
        assert "type_b" in types

    def test_duplicate_registration_raises(self):
        from app.sdk.agent_sdk import AgentRegistry, AgentSDK

        class DupAgent(AgentSDK):
            agent_type = "dup_agent"
            async def handle_task(self, p: dict) -> dict: return {}

        AgentRegistry.register(DupAgent)
        with pytest.raises(ValueError, match="already registered"):
            AgentRegistry.register(DupAgent)

    def test_missing_agent_type_raises(self):
        from app.sdk.agent_sdk import AgentRegistry, AgentSDK

        class NoTypeAgent(AgentSDK):
            agent_type = ""  # not set
            async def handle_task(self, p: dict) -> dict: return {}

        with pytest.raises(ValueError, match="must set agent_type"):
            AgentRegistry.register(NoTypeAgent)

    def test_unregister_removes_type(self):
        from app.sdk.agent_sdk import AgentRegistry, AgentSDK

        class TempAgent(AgentSDK):
            agent_type = "temp_agent"
            async def handle_task(self, p: dict) -> dict: return {}

        AgentRegistry.register(TempAgent)
        AgentRegistry.unregister("temp_agent")
        assert AgentRegistry.get("temp_agent") is None


# ---------------------------------------------------------------------------
# AgentSDK lifecycle and task dispatch
# ---------------------------------------------------------------------------


class ConcreteAgent:
    """Concrete AgentSDK for testing — defined at module level for reuse."""


def _make_concrete_agent(**kwargs):
    """Build a minimal concrete AgentSDK subclass."""
    from app.sdk.agent_sdk import AgentSDK

    class _Agent(AgentSDK):
        agent_type = "test_concrete"

        async def handle_task(self, task_payload: dict) -> dict:
            return {"handled": True, "payload": task_payload}

    return _Agent(**kwargs)


class TestAgentSDKLifecycle:
    @pytest.mark.asyncio
    async def test_on_start_is_noop_by_default(self):
        agent = _make_concrete_agent()
        # Should not raise
        await agent.on_start()

    @pytest.mark.asyncio
    async def test_on_stop_is_noop_by_default(self):
        agent = _make_concrete_agent()
        await agent.on_stop()

    @pytest.mark.asyncio
    async def test_on_error_logs_and_does_not_raise(self):
        agent = _make_concrete_agent()
        exc = RuntimeError("test error")
        # Should not raise
        await agent.on_error({"task": "x"}, exc)

    @pytest.mark.asyncio
    async def test_dispatch_calls_handle_task(self):
        agent = _make_concrete_agent()
        result = await agent.dispatch({"key": "value"})
        assert result["handled"] is True
        assert result["payload"] == {"key": "value"}

    @pytest.mark.asyncio
    async def test_dispatch_catches_exception_from_handle_task(self):
        from app.sdk.agent_sdk import AgentSDK

        class BrokenAgent(AgentSDK):
            agent_type = "broken_agent_test"

            async def handle_task(self, task_payload: dict) -> dict:
                raise ValueError("intentional failure")

        agent = BrokenAgent()
        result = await agent.dispatch({"x": 1})
        assert result["success"] is False
        assert "intentional failure" in result["error"]

    def test_agent_id_auto_generated(self):
        agent = _make_concrete_agent()
        # Should be a valid UUID string
        parsed = uuid.UUID(agent.agent_id)
        assert str(parsed) == agent.agent_id

    def test_agent_id_can_be_overridden(self):
        fixed_id = str(uuid.uuid4())
        agent = _make_concrete_agent(agent_id=fixed_id)
        assert agent.agent_id == fixed_id


# ---------------------------------------------------------------------------
# AgentSDK.call_tool()
# ---------------------------------------------------------------------------


class TestAgentSDKCallTool:
    @pytest.mark.asyncio
    async def test_call_tool_delegates_to_registry(self):
        agent = _make_concrete_agent()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = {"answer": 42}

        agent._tool_registry.execute = AsyncMock(return_value=mock_result)

        result = await agent.call_tool("my_tool", {"param": "value"})

        assert result.output == {"answer": 42}
        agent._tool_registry.execute.assert_awaited_once()
        call_args = agent._tool_registry.execute.call_args[0][0]
        assert call_args.tool_name == "my_tool"
        assert call_args.parameters == {"param": "value"}
        assert str(call_args.agent_id) == agent.agent_id

    @pytest.mark.asyncio
    async def test_call_tool_passes_idempotency_key(self):
        agent = _make_concrete_agent()

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.output = {}
        agent._tool_registry.execute = AsyncMock(return_value=mock_result)

        await agent.call_tool("my_tool", {}, idempotency_key="key-abc")

        call_args = agent._tool_registry.execute.call_args[0][0]
        assert call_args.idempotency_key == "key-abc"


# ---------------------------------------------------------------------------
# SDK __init__ re-exports
# ---------------------------------------------------------------------------


class TestSDKPublicApi:
    def test_tool_sdk_importable(self):
        from app.sdk import ToolSDK
        assert ToolSDK is not None

    def test_sdk_tool_importable(self):
        from app.sdk import sdk_tool
        assert sdk_tool is not None

    def test_register_tool_importable(self):
        from app.sdk import register_tool
        assert register_tool is not None

    def test_agent_sdk_importable(self):
        from app.sdk import AgentSDK
        assert AgentSDK is not None

    def test_tool_definition_importable(self):
        from app.sdk import ToolDefinition
        assert ToolDefinition is not None

    def test_tool_call_request_importable(self):
        from app.sdk import ToolCallRequest
        assert ToolCallRequest is not None

    def test_tool_call_result_importable(self):
        from app.sdk import ToolCallResult
        assert ToolCallResult is not None
