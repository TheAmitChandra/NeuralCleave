"""Unit tests for NeuralCleave.tools.registry — ToolRegistry dispatch and schema."""

from __future__ import annotations

import pytest

from neuralcleave.tools.base import Tool, ToolResult
from neuralcleave.tools.registry import ToolRegistry


class _SessionAwareTool(Tool):
    """Records whatever kwargs it was actually called with."""

    name = "session_aware_tool"
    description = "Captures its call kwargs for assertions."
    permissions = []

    def __init__(self) -> None:
        self.received: dict = {}

    async def execute(self, **kwargs) -> ToolResult:
        self.received = kwargs
        return ToolResult(tool=self.name, output="ok")

# ---------------------------------------------------------------------------
# Stub tools
# ---------------------------------------------------------------------------


class _OkTool(Tool):
    name = "ok_tool"
    description = "Always succeeds."
    permissions = ["network"]

    async def execute(self, **_) -> ToolResult:
        return ToolResult(tool=self.name, output="done")


class _FailTool(Tool):
    name = "fail_tool"
    description = "Always raises."
    permissions = []

    async def execute(self, **_) -> ToolResult:
        raise RuntimeError("intentional failure")


class _FreeTool(Tool):
    name = "free_tool"
    description = "No permissions."
    permissions = []

    async def execute(self, **_) -> ToolResult:
        return ToolResult(tool=self.name, output="free")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_register_and_get():
    reg = ToolRegistry()
    reg.register(_OkTool())
    assert reg.get("ok_tool") is not None


def test_get_missing_returns_none():
    reg = ToolRegistry()
    assert reg.get("nope") is None


def test_unregister_removes_tool():
    reg = ToolRegistry()
    reg.register(_OkTool())
    reg.unregister("ok_tool")
    assert reg.get("ok_tool") is None


def test_names_are_sorted():
    reg = ToolRegistry()
    reg.register(_OkTool())
    reg.register(_FreeTool())
    assert reg.names == sorted(reg.names)


def test_register_overwrites_existing():
    reg = ToolRegistry()
    reg.register(_OkTool())
    reg.register(_OkTool())  # same name — should not raise
    assert len(reg.names) == 1


# ---------------------------------------------------------------------------
# Call — success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_success():
    reg = ToolRegistry()
    reg.register(_OkTool())
    result = await reg.call("ok_tool", {})
    assert result.success
    assert result.output == "done"


@pytest.mark.asyncio
async def test_call_tool_not_found_returns_error():
    reg = ToolRegistry()
    result = await reg.call("missing", {})
    assert not result.success
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_call_wraps_unhandled_exception():
    reg = ToolRegistry()
    reg.register(_FailTool())
    result = await reg.call("fail_tool", {})
    assert not result.success
    assert "intentional failure" in (result.error or "")


# ---------------------------------------------------------------------------
# Permission checking
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_permission_denied_when_not_in_allowed():
    reg = ToolRegistry(allowed_permissions=set())  # empty whitelist
    reg.register(_OkTool())  # needs "network"
    result = await reg.call("ok_tool", {})
    assert not result.success
    assert "Permission denied" in (result.error or "")


@pytest.mark.asyncio
async def test_call_permission_granted_when_in_allowed():
    reg = ToolRegistry(allowed_permissions={"network"})
    reg.register(_OkTool())
    result = await reg.call("ok_tool", {})
    assert result.success


@pytest.mark.asyncio
async def test_call_bypass_permission_check():
    reg = ToolRegistry(allowed_permissions=set())
    reg.register(_OkTool())
    result = await reg.call("ok_tool", {}, check_permissions=False)
    assert result.success


@pytest.mark.asyncio
async def test_call_none_allowed_grants_all():
    # allowed_permissions=None means "grant everything"
    reg = ToolRegistry(allowed_permissions=None)
    reg.register(_OkTool())
    result = await reg.call("ok_tool", {})
    assert result.success


# ---------------------------------------------------------------------------
# Call — session_id forwarding (round 4, 2026-08-21 gap analysis P0)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_call_forwards_session_id_as_underscore_session_id():
    reg = ToolRegistry()
    tool = _SessionAwareTool()
    reg.register(tool)
    await reg.call("session_aware_tool", {}, session_id="s1")
    assert tool.received.get("_session_id") == "s1"


@pytest.mark.asyncio
async def test_call_without_session_id_does_not_add_the_key():
    reg = ToolRegistry()
    tool = _SessionAwareTool()
    reg.register(tool)
    await reg.call("session_aware_tool", {})
    assert "_session_id" not in tool.received


@pytest.mark.asyncio
async def test_call_does_not_override_an_explicit_session_id_argument():
    reg = ToolRegistry()
    tool = _SessionAwareTool()
    reg.register(tool)
    await reg.call("session_aware_tool", {"_session_id": "explicit"}, session_id="from_registry")
    assert tool.received.get("_session_id") == "explicit"


@pytest.mark.asyncio
async def test_call_does_not_mutate_the_caller_arguments_dict():
    reg = ToolRegistry()
    reg.register(_SessionAwareTool())
    arguments = {"command": "ls"}
    await reg.call("session_aware_tool", arguments, session_id="s1")
    assert "_session_id" not in arguments


# ---------------------------------------------------------------------------
# default() — require_approval wiring (round 4, 2026-08-21 gap analysis P0)
# ---------------------------------------------------------------------------


def test_default_shell_tool_require_approval_off_by_default():
    """Regression guard: before this, ShellTool() in default() always used
    its own default (False) with no way to turn it on — ApprovalPolicy and
    the whole exec-approval gate were unreachable in production."""
    registry = ToolRegistry.default()
    shell = registry.get("shell")
    assert shell._require_approval is False


def test_default_require_approval_true_reaches_shell_tool():
    registry = ToolRegistry.default(require_approval=True)
    shell = registry.get("shell")
    assert shell._require_approval is True


def test_default_require_approval_true_reaches_browser_tool():
    registry = ToolRegistry.default(require_approval=True)
    browser = registry.get("browser")
    assert browser._require_approval is True


# ---------------------------------------------------------------------------
# Schema export
# ---------------------------------------------------------------------------


def test_all_schemas_returns_list():
    reg = ToolRegistry()
    reg.register(_OkTool())
    reg.register(_FreeTool())
    schemas = reg.all_schemas()
    assert len(schemas) == 2
    names = {s["name"] for s in schemas}
    assert "ok_tool" in names
    assert "free_tool" in names


def test_tools_prompt_block_contains_names():
    reg = ToolRegistry()
    reg.register(_OkTool())
    block = reg.tools_prompt_block()
    assert "ok_tool" in block


def test_tools_prompt_block_empty_registry():
    reg = ToolRegistry()
    assert "No tools" in reg.tools_prompt_block()


# ---------------------------------------------------------------------------
# Default factory
# ---------------------------------------------------------------------------


def test_default_registry_loads_builtin_tools():
    reg = ToolRegistry.default()
    assert "web_search" in reg.names
    assert "file_ops" in reg.names


def test_default_registry_includes_canvas_tool():
    reg = ToolRegistry.default()
    assert "canvas" in reg.names


def test_canvas_tool_schema_exported():
    reg = ToolRegistry.default()
    schemas = reg.all_schemas()
    canvas_schema = next((s for s in schemas if s["name"] == "canvas"), None)
    assert canvas_schema is not None
    assert "description" in canvas_schema


def test_default_registry_canvas_in_prompt_block():
    reg = ToolRegistry.default()
    block = reg.tools_prompt_block()
    assert "canvas" in block


@pytest.mark.asyncio
async def test_default_registry_canvas_status_with_no_renderer():
    reg = ToolRegistry.default()
    result = await reg.call("canvas", {"action": "status"})
    # renderer not set in test environment → error expected
    assert result.error is not None
    assert "not initialised" in (result.error or "").lower() or not result.success
