"""File operations tool — safe read, write, list within a sandboxed root.

All paths are resolved relative to a configurable root directory (default
``~/cortexflow_files/``).  Absolute paths and ``..`` traversal are rejected,
so the agent can never escape the sandbox.

Permissions declared: ``filesystem:read`` and ``filesystem:write``.

Usage::

    tool = FileOpsTool()

    # Read
    result = await tool.execute(operation="read", path="notes/todo.md")

    # Write
    result = await tool.execute(
        operation="write",
        path="notes/todo.md",
        content="- Buy milk\n",
    )

    # List
    result = await tool.execute(operation="list", path="notes/")
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from cortexflow.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path.home() / "cortexflow_files"


class FileOpsTool(Tool):
    """Read, write, and list files within a sandboxed directory."""

    name = "file_ops"
    description = (
        "Read, write, or list files on the local filesystem. "
        "Paths are always relative to a safe working directory — "
        "no absolute paths or directory traversal allowed."
    )
    parameters = {
        "operation": {
            "type": "str",
            "description": "Operation: 'read' | 'write' | 'list' | 'delete'.",
            "required": True,
        },
        "path": {
            "type": "str",
            "description": "Relative file or directory path within the sandbox.",
            "required": True,
        },
        "content": {
            "type": "str",
            "description": "Content to write (only used with 'write' operation).",
            "required": False,
        },
    }
    permissions = ["filesystem:read", "filesystem:write"]

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(root) if root else DEFAULT_ROOT
        self._root.mkdir(parents=True, exist_ok=True)

    async def execute(
        self,
        operation: str,
        path: str,
        content: str = "",
        **_: Any,
    ) -> ToolResult:
        try:
            resolved = self._resolve(path)
        except ValueError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

        op = operation.lower().strip()

        if op == "read":
            return self._read(resolved)
        if op == "write":
            return self._write(resolved, content)
        if op == "list":
            return self._list(resolved)
        if op == "delete":
            return self._delete(resolved)

        return ToolResult(
            tool=self.name,
            output=None,
            error=f"Unknown operation {operation!r}. Use: read | write | list | delete",
        )

    # ------------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        """Resolve path strictly within root. Raise ValueError on traversal."""
        # Reject any absolute path
        if os.path.isabs(path):
            raise ValueError(f"Absolute paths not allowed: {path!r}")
        resolved = (self._root / path).resolve()
        # Ensure it's still inside root
        try:
            resolved.relative_to(self._root.resolve())
        except ValueError:
            raise ValueError(f"Path traversal not allowed: {path!r}")
        return resolved

    def _read(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None, error=f"File not found: {path.name}")
        if path.is_dir():
            return ToolResult(tool=self.name, output=None, error=f"{path.name} is a directory; use 'list'")
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            return ToolResult(
                tool=self.name,
                output=text,
                metadata={"path": str(path.relative_to(self._root)), "size": len(text)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _write(self, path: Path, content: str) -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                tool=self.name,
                output=f"Written {len(content)} chars to {path.relative_to(self._root)}",
                metadata={"path": str(path.relative_to(self._root)), "size": len(content)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _list(self, path: Path) -> ToolResult:
        target = path if path.is_dir() else path.parent
        if not target.exists():
            return ToolResult(tool=self.name, output=None, error=f"Directory not found: {target.name}")
        try:
            entries = [
                {
                    "name": e.name,
                    "type": "dir" if e.is_dir() else "file",
                    "size": e.stat().st_size if e.is_file() else None,
                }
                for e in sorted(target.iterdir())
            ]
            return ToolResult(
                tool=self.name,
                output=entries,
                metadata={"directory": str(target.relative_to(self._root))},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _delete(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None, error=f"Not found: {path.name}")
        if path.is_dir():
            return ToolResult(
                tool=self.name, output=None,
                error="Directory deletion not supported for safety; delete files individually."
            )
        try:
            path.unlink()
            return ToolResult(
                tool=self.name,
                output=f"Deleted {path.relative_to(self._root)}",
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))
