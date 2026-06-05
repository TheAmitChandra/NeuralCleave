"""Unit tests for the tool subsystem.

All external I/O (HTTP, subprocesses, Playwright, SQLAlchemy) is mocked.
Tests run fully offline.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.tools.registry import (
    ToolCallRequest,
    ToolDefinition,
    ToolRegistry,
    calculate_risk_score,
    resolve_isolation_tier,
)
from app.core.tools.filesystem import (
    _resolve_safe,
    file_read,
    file_write,
    file_list,
    file_search,
)
from app.core.tools.shell import (
    ALLOWED_COMMANDS,
    _parse_command,
    _validate_command,
    shell_execute,
)
from app.core.tools.api_caller import _sanitise_headers_for_log
from app.core.tools.database_tool import _validate_select_only


# ===========================================================================
# ToolRegistry tests
# ===========================================================================

class TestToolRegistry:
    """Tests for ToolRegistry core logic."""

    def _make_registry(self) -> ToolRegistry:
        """Return a fresh (non-singleton) registry for test isolation."""
        reg = ToolRegistry()
        return reg

    def _simple_def(self, name: str = "test.tool", risk_level: str = "low") -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description="test",
            permissions=["file.read"],
            risk_level=risk_level,  # type: ignore[arg-type]
        )

    def test_register_and_list(self):
        reg = self._make_registry()
        defn = self._simple_def()
        reg.register(defn, AsyncMock())
        tools = reg.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "test.tool"

    def test_register_duplicate_raises(self):
        reg = self._make_registry()
        defn = self._simple_def()
        reg.register(defn, AsyncMock())
        with pytest.raises(ValueError, match="already registered"):
            reg.register(defn, AsyncMock())

    def test_singleton_registers_default_tools(self):
        reg = ToolRegistry.get_instance()
        assert reg.get_definition("browser.navigate") is not None
        assert reg.get_definition("shell.execute") is not None
        assert reg.get_definition("file.read") is not None
        assert reg.get_definition("file.write") is not None
        assert reg.get_definition("api.get") is not None
        assert reg.get_definition("api.post") is not None
        assert reg.get_definition("db.query") is not None

    @pytest.mark.asyncio
    async def test_singleton_db_query_execution_mocked(self):
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id"]
        mock_result.fetchmany.return_value = [(1,)]

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.execute.return_value = mock_result
        mock_session_local = MagicMock(return_value=mock_session)

        reg = ToolRegistry.get_instance()

        with patch("app.db.postgres.AsyncSessionLocal", mock_session_local):
            req = ToolCallRequest(
                tool_name="db.query",
                agent_id=uuid.uuid4(),
                parameters={"sql": "SELECT * FROM users"},
            )
            result = await reg.execute(req)

            assert result.success is True
            assert result.output is not None
            assert "row_count" in result.output
            assert result.output["row_count"] == 1
            assert result.output["rows"] == [{"id": 1}]
            mock_session.execute.assert_called()

    def test_get_definition_returns_none_for_unknown(self):
        reg = self._make_registry()
        assert reg.get_definition("does.not.exist") is None

    def test_check_permissions_ok(self):
        reg = self._make_registry()
        defn = self._simple_def()
        ok, missing = reg.check_permissions(defn, ["file.read", "db.read"])
        assert ok is True
        assert missing == []

    def test_check_permissions_missing(self):
        reg = self._make_registry()
        defn = self._simple_def()
        ok, missing = reg.check_permissions(defn, [])
        assert ok is False
        assert "file.read" in missing

    @pytest.mark.asyncio
    async def test_execute_unknown_tool_returns_error(self):
        reg = self._make_registry()
        req = ToolCallRequest(tool_name="no.such.tool", agent_id=uuid.uuid4(), parameters={})
        result = await reg.execute(req)
        assert result.success is False
        assert "Unknown tool" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_permission_denied(self):
        reg = self._make_registry()
        defn = self._simple_def()
        reg.register(defn, AsyncMock(return_value="ok"))
        req = ToolCallRequest(tool_name="test.tool", agent_id=uuid.uuid4(), parameters={})
        result = await reg.execute(req, agent_permissions=[])
        assert result.success is False
        assert "Permission denied" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_calls_handler_on_success(self):
        reg = self._make_registry()
        handler = AsyncMock(return_value={"answer": 42})
        defn = self._simple_def()
        reg.register(defn, handler)
        req = ToolCallRequest(tool_name="test.tool", agent_id=uuid.uuid4(), parameters={"x": 1})
        result = await reg.execute(req, agent_permissions=["file.read"])
        assert result.success is True
        assert result.output == {"answer": 42}
        handler.assert_called_once_with({"x": 1})

    @pytest.mark.asyncio
    async def test_execute_dry_run_does_not_call_handler(self):
        reg = self._make_registry()
        handler = AsyncMock(return_value="should not be called")
        defn = self._simple_def()
        reg.register(defn, handler)
        req = ToolCallRequest(tool_name="test.tool", agent_id=uuid.uuid4(), parameters={})
        result = await reg.execute(req, agent_permissions=["file.read"], dry_run=True)
        handler.assert_not_called()
        assert result.output == {"dry_run": True, "predicted_isolation": result.isolation_tier}

    @pytest.mark.asyncio
    async def test_execute_handler_exception_returns_error(self):
        reg = self._make_registry()
        handler = AsyncMock(side_effect=RuntimeError("disk full"))
        defn = self._simple_def()
        reg.register(defn, handler)
        req = ToolCallRequest(tool_name="test.tool", agent_id=uuid.uuid4(), parameters={})
        result = await reg.execute(req, agent_permissions=["file.read"])
        assert result.success is False
        assert "disk full" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_high_risk_requires_approval(self):
        reg = self._make_registry()
        defn = ToolDefinition(
            name="critical.tool",
            description="very dangerous",
            permissions=[],
            risk_level="critical",
            requires_approval=True,
        )
        reg.register(defn, AsyncMock())
        req = ToolCallRequest(tool_name="critical.tool", agent_id=uuid.uuid4(), parameters={})
        result = await reg.execute(req, agent_permissions=[])
        assert result.requires_approval is True
        assert result.success is False


class TestRiskScoring:
    """Tests for risk scoring and isolation tier helpers."""

    def test_low_risk_base(self):
        defn = ToolDefinition(name="t", description="", permissions=[], risk_level="low")
        assert calculate_risk_score(defn) == 10.0

    def test_critical_risk_base(self):
        defn = ToolDefinition(name="t", description="", permissions=[], risk_level="critical")
        assert calculate_risk_score(defn) == 90.0

    def test_permissions_add_to_score(self):
        defn = ToolDefinition(
            name="t", description="", permissions=["shell.execute", "file.write"], risk_level="low"
        )
        score = calculate_risk_score(defn)
        assert score == 10.0 + 20.0 + 15.0  # base + shell + file.write

    def test_score_capped_at_100(self):
        defn = ToolDefinition(
            name="t",
            description="",
            permissions=["shell.execute", "file.write", "db.write", "network.external", "comms.send"],
            risk_level="critical",
        )
        assert calculate_risk_score(defn) == 100.0

    def test_isolation_tiers(self):
        assert resolve_isolation_tier(10) == "process"
        assert resolve_isolation_tier(25) == "process"
        assert resolve_isolation_tier(26) == "container"
        assert resolve_isolation_tier(60) == "container"
        assert resolve_isolation_tier(61) == "isolated_container"
        assert resolve_isolation_tier(85) == "isolated_container"
        assert resolve_isolation_tier(86) == "blocked"
        assert resolve_isolation_tier(100) == "blocked"


# ===========================================================================
# Filesystem tool tests
# ===========================================================================

class TestFilesystemTools:
    """Tests for file tool path safety and basic I/O."""

    def test_resolve_safe_accepts_valid_path(self, tmp_path: Path):
        result = _resolve_safe("subdir/file.txt", str(tmp_path))
        assert str(result).startswith(str(tmp_path))

    def test_resolve_safe_blocks_traversal(self, tmp_path: Path):
        with pytest.raises(PermissionError, match="traversal"):
            _resolve_safe("../../etc/passwd", str(tmp_path))

    def test_resolve_safe_blocks_absolute_escape(self, tmp_path: Path):
        with pytest.raises(PermissionError, match="traversal"):
            _resolve_safe("/etc/shadow", str(tmp_path))

    @pytest.mark.asyncio
    async def test_file_read_returns_content(self, tmp_path: Path):
        target = tmp_path / "notes.txt"
        target.write_text("hello world")
        result = await file_read({"path": "notes.txt", "workspace_root": str(tmp_path)})
        assert result["content"] == "hello world"
        assert result["truncated"] is False

    @pytest.mark.asyncio
    async def test_file_read_missing_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            await file_read({"path": "missing.txt", "workspace_root": str(tmp_path)})

    @pytest.mark.asyncio
    async def test_file_read_truncates_large_file(self, tmp_path: Path):
        target = tmp_path / "big.txt"
        target.write_bytes(b"x" * 100)
        result = await file_read({
            "path": "big.txt",
            "workspace_root": str(tmp_path),
            "max_bytes": 50,
        })
        assert result["truncated"] is True
        assert len(result["content"]) == 50

    @pytest.mark.asyncio
    async def test_file_write_creates_file(self, tmp_path: Path):
        result = await file_write({
            "path": "output.txt",
            "workspace_root": str(tmp_path),
            "content": "written by agent",
        })
        assert (tmp_path / "output.txt").read_text() == "written by agent"
        assert result["size_bytes"] > 0

    @pytest.mark.asyncio
    async def test_file_write_blocks_traversal(self, tmp_path: Path):
        with pytest.raises(PermissionError):
            await file_write({
                "path": "../../evil.sh",
                "workspace_root": str(tmp_path),
                "content": "rm -rf /",
            })

    @pytest.mark.asyncio
    async def test_file_list_returns_entries(self, tmp_path: Path):
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        result = await file_list({"workspace_root": str(tmp_path), "pattern": "*.txt"})
        names = [e["name"] for e in result["entries"]]
        assert "a.txt" in names
        assert "b.txt" in names

    @pytest.mark.asyncio
    async def test_file_search_finds_matches(self, tmp_path: Path):
        (tmp_path / "code.py").write_text("def my_function():\n    pass\n")
        result = await file_search({
            "workspace_root": str(tmp_path),
            "query": "my_function",
        })
        assert len(result["matches"]) == 1
        assert result["matches"][0]["line_number"] == 1


# ===========================================================================
# Shell tool tests
# ===========================================================================

class TestShellTools:
    """Tests for command allowlist and execution."""

    def test_parse_command_splits_args(self):
        argv = _parse_command("python -m pytest tests/")
        assert argv == ["python", "-m", "pytest", "tests/"]

    def test_validate_command_allows_listed(self):
        _validate_command(["python", "--version"])  # should not raise

    def test_validate_command_blocks_unlisted(self):
        with pytest.raises(PermissionError, match="not in the allowed"):
            _validate_command(["rm", "-rf", "/"])

    def test_validate_command_blocks_empty(self):
        with pytest.raises(ValueError, match="Empty"):
            _validate_command([])

    def test_validate_command_blocks_git_write(self):
        with pytest.raises(PermissionError, match="not allowed"):
            _validate_command(["git", "push", "origin", "main"])

    def test_validate_command_allows_git_read(self):
        _validate_command(["git", "log", "--oneline", "-5"])  # should not raise

    @pytest.mark.asyncio
    async def test_shell_execute_blocked_command(self, tmp_path: Path):
        with pytest.raises(PermissionError):
            await shell_execute({
                "command": "rm -rf .",
                "workspace_root": str(tmp_path),
            })

    @pytest.mark.asyncio
    async def test_shell_execute_runs_echo(self, tmp_path: Path):
        result = await shell_execute({
            "command": "python -c \"print('hello')\"",
            "workspace_root": str(tmp_path),
        })
        assert result["exit_code"] == 0
        assert "hello" in result["stdout"]
        assert result["timed_out"] is False


# ===========================================================================
# API caller tests
# ===========================================================================

class TestApiCaller:
    """Tests for HTTP tool header scrubbing."""

    def test_sanitise_auth_header(self):
        headers = {
            "Authorization": "Bearer secret-token",
            "Content-Type": "application/json",
            "X-API-Key": "my-key",
        }
        sanitised = _sanitise_headers_for_log(headers)
        assert sanitised["Authorization"] == "***"
        assert sanitised["X-API-Key"] == "***"
        assert sanitised["Content-Type"] == "application/json"

    def test_sanitise_preserves_non_sensitive(self):
        headers = {"Accept": "application/json", "X-Custom": "value"}
        sanitised = _sanitise_headers_for_log(headers)
        assert sanitised == headers


# ===========================================================================
# Database tool tests
# ===========================================================================

class TestDatabaseTool:
    """Tests for SQL validation (select-only guard)."""

    def test_valid_select_passes(self):
        _validate_select_only("SELECT id, name FROM users WHERE id = :uid")

    def test_select_with_cte_passes(self):
        _validate_select_only("WITH cte AS (SELECT 1) SELECT * FROM cte")

    def test_insert_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("INSERT INTO users VALUES ('x')")

    def test_update_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("UPDATE users SET role = 'admin'")

    def test_delete_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("DELETE FROM audit_logs")

    def test_drop_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("DROP TABLE users")

    def test_truncate_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("TRUNCATE TABLE users")

    def test_exec_blocked(self):
        with pytest.raises(PermissionError, match="SELECT"):
            _validate_select_only("EXEC sp_dangerous")

    def test_leading_whitespace_insert_blocked(self):
        with pytest.raises(PermissionError):
            _validate_select_only("  \n  INSERT INTO t VALUES (1)")
