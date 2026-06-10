"""Unit tests for cortexflow.tools.registry — ToolRegistry dispatch and schema."""

from __future__ import annotations

import pytest

from cortexflow.tools.base import Tool, ToolResult
from cortexflow.tools.registry import ToolRegistry

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
