"""File operations tool — read, write, list, search, move, copy, mkdir, stat, append.

By default all paths must fall inside ``root`` (``~/NeuralCleave_files/``), so the
agent cannot escape the sandbox.  Pass ``allowed_paths`` to extend access to
additional directories without disabling safety checks on ``root``.

Operations
----------
read    — read a text file (UTF-8; capped at 512 KB)
write   — write (overwrite) a text file
append  — append text to a file
list    — list a directory with name/type/size
delete  — delete a single file
move    — move or rename a file or directory
copy    — copy a file to a new location
mkdir   — create a directory tree
stat    — file/directory metadata (size, modified, created, type)
search  — glob pattern search within an allowed tree

Usage::

    tool = FileOpsTool()

    result = await tool.execute(operation="read", path="notes/todo.md")
    result = await tool.execute(operation="write", path="out.txt", content="hello")
    result = await tool.execute(operation="append", path="log.txt", content="line\\n")
    result = await tool.execute(operation="list", path="notes/")
    result = await tool.execute(operation="move", path="old.txt", destination="new.txt")
    result = await tool.execute(operation="copy", path="src.txt", destination="dst.txt")
    result = await tool.execute(operation="mkdir", path="reports/2026")
    result = await tool.execute(operation="stat", path="notes/todo.md")
    result = await tool.execute(operation="search", path=".", pattern="**/*.md")
    result = await tool.execute(operation="delete", path="junk.txt")

Expanded access::

    # Allow the agent to also read/write ~/projects in addition to the default sandbox
    tool = FileOpsTool(allowed_paths=["~/projects"])
    result = await tool.execute(operation="list", path="~/projects")
"""

from __future__ import annotations

import asyncio
import fnmatch
import logging
import shutil
import time
from pathlib import Path
from typing import Any

from neuralcleave.tools.base import Tool, ToolResult

logger = logging.getLogger(__name__)

DEFAULT_ROOT = Path.home() / "NeuralCleave_files"
_MAX_READ_BYTES = 512 * 1024  # 512 KB cap to keep responses manageable


class FileOpsTool(Tool):
    """Read, write, list, search, move, copy, mkdir, stat, and append files.

    Args:
        root:          Primary sandbox directory.  Relative paths are anchored here.
                       Defaults to ``~/NeuralCleave_files/``.
        allowed_paths: Extra directories the tool may access.  Each entry is
                       expanded (``~``) and resolved to an absolute path.
    """

    name = "file_ops"
    description = (
        "Read, write, list, search, move, copy, mkdir, stat, and append files "
        "on the local filesystem.  Access is limited to configured safe directories."
    )
    parameters = {
        "operation": {
            "type": "str",
            "description": (
                "Operation: 'read' | 'write' | 'append' | 'list' | 'delete' | "
                "'move' | 'copy' | 'mkdir' | 'stat' | 'search'."
            ),
            "required": True,
        },
        "path": {
            "type": "str",
            "description": "File or directory path (relative to root, or absolute if in allowed_paths).",
            "required": True,
        },
        "content": {
            "type": "str",
            "description": "Text content for 'write' and 'append' operations.",
            "required": False,
        },
        "destination": {
            "type": "str",
            "description": "Target path for 'move' and 'copy' operations.",
            "required": False,
        },
        "pattern": {
            "type": "str",
            "description": "Glob pattern for 'search' (e.g. '**/*.py'). Defaults to '*'.",
            "required": False,
        },
    }
    permissions = ["filesystem:read", "filesystem:write"]

    def __init__(
        self,
        root: Path | str | None = None,
        allowed_paths: list[str | Path] | None = None,
    ) -> None:
        self._root = Path(root).expanduser().resolve() if root else DEFAULT_ROOT.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

        self._allowed_roots: list[Path] = [self._root]
        for extra in allowed_paths or []:
            resolved = Path(extra).expanduser().resolve()
            if resolved not in self._allowed_roots:
                self._allowed_roots.append(resolved)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        operation: str,
        path: str,
        content: str = "",
        destination: str = "",
        pattern: str = "*",
        **_: Any,
    ) -> ToolResult:
        op = operation.lower().strip()

        # Single-path operations
        if op in {"read", "write", "append", "list", "delete", "mkdir", "stat"}:
            try:
                resolved = self._resolve(path)
            except ValueError as exc:
                return ToolResult(tool=self.name, output=None, error=str(exc))

            if op == "read":
                return await asyncio.to_thread(self._read, resolved)
            if op == "write":
                return await asyncio.to_thread(self._write, resolved, content)
            if op == "append":
                return await asyncio.to_thread(self._append, resolved, content)
            if op == "list":
                return await asyncio.to_thread(self._list, resolved)
            if op == "delete":
                return await asyncio.to_thread(self._delete, resolved)
            if op == "mkdir":
                return await asyncio.to_thread(self._mkdir, resolved)
            if op == "stat":
                return await asyncio.to_thread(self._stat, resolved)

        # Two-path operations
        if op in {"move", "copy"}:
            if not destination:
                return ToolResult(
                    tool=self.name, output=None,
                    error=f"'destination' is required for the '{op}' operation",
                )
            try:
                src = self._resolve(path)
                dst = self._resolve(destination)
            except ValueError as exc:
                return ToolResult(tool=self.name, output=None, error=str(exc))

            if op == "move":
                return await asyncio.to_thread(self._move, src, dst)
            return await asyncio.to_thread(self._copy, src, dst)

        if op == "search":
            try:
                search_root = self._resolve(path)
            except ValueError as exc:
                return ToolResult(tool=self.name, output=None, error=str(exc))
            return await asyncio.to_thread(self._search, search_root, pattern)

        return ToolResult(
            tool=self.name,
            output=None,
            error=(
                f"Unknown operation {operation!r}. "
                "Use: read | write | append | list | delete | move | copy | mkdir | stat | search"
            ),
        )

    # ------------------------------------------------------------------
    # Path resolution helpers
    # ------------------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        p = Path(path).expanduser()
        resolved = (self._root / p).resolve() if not p.is_absolute() else p.resolve()
        if not self._is_allowed(resolved):
            allowed = ", ".join(str(r) for r in self._allowed_roots)
            raise ValueError(
                f"Path {path!r} is outside all allowed directories ({allowed}). "
                "Use a relative path or add the directory to allowed_paths."
            )
        return resolved

    def _is_allowed(self, resolved: Path) -> bool:
        for root in self._allowed_roots:
            try:
                resolved.relative_to(root)
                return True
            except ValueError:
                continue
        return False

    def _rel(self, path: Path) -> str:
        """Best-effort relative display path."""
        for root in self._allowed_roots:
            try:
                return str(path.relative_to(root))
            except ValueError:
                continue
        return str(path)

    # ------------------------------------------------------------------
    # Operation implementations
    # ------------------------------------------------------------------

    def _read(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"File not found: {self._rel(path)}")
        if path.is_dir():
            return ToolResult(tool=self.name, output=None,
                              error=f"{self._rel(path)} is a directory; use 'list'")
        try:
            raw = path.read_bytes()
            truncated = len(raw) > _MAX_READ_BYTES
            text = raw[:_MAX_READ_BYTES].decode("utf-8", errors="replace")
            return ToolResult(
                tool=self.name,
                output=text,
                metadata={
                    "path": self._rel(path),
                    "size": path.stat().st_size,
                    "truncated": truncated,
                },
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _write(self, path: Path, content: str) -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return ToolResult(
                tool=self.name,
                output=f"Written {len(content)} chars to {self._rel(path)}",
                metadata={"path": self._rel(path), "size": len(content)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _append(self, path: Path, content: str) -> ToolResult:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(content)
            return ToolResult(
                tool=self.name,
                output=f"Appended {len(content)} chars to {self._rel(path)}",
                metadata={"path": self._rel(path), "appended": len(content)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _list(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Not found: {self._rel(path)}")
        target = path if path.is_dir() else path.parent
        if not target.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Directory not found: {self._rel(target)}")
        try:
            entries = sorted(target.iterdir(), key=lambda e: (e.is_file(), e.name))
            items = [
                {
                    "name": e.name,
                    "type": "dir" if e.is_dir() else "file",
                    "size": e.stat().st_size if e.is_file() else None,
                }
                for e in entries
            ]
            return ToolResult(
                tool=self.name,
                output=items,
                metadata={"directory": self._rel(target), "count": len(items)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _delete(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Not found: {self._rel(path)}")
        if path.is_dir():
            return ToolResult(
                tool=self.name, output=None,
                error="Directory deletion not supported for safety; delete files individually.",
            )
        try:
            path.unlink()
            return ToolResult(
                tool=self.name,
                output=f"Deleted {self._rel(path)}",
                metadata={"path": self._rel(path)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _move(self, src: Path, dst: Path) -> ToolResult:
        if not src.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Source not found: {self._rel(src)}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
            return ToolResult(
                tool=self.name,
                output=f"Moved {self._rel(src)} → {self._rel(dst)}",
                metadata={"source": self._rel(src), "destination": self._rel(dst)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _copy(self, src: Path, dst: Path) -> ToolResult:
        if not src.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Source not found: {self._rel(src)}")
        if src.is_dir():
            return ToolResult(tool=self.name, output=None,
                              error="Directory copy not supported; copy files individually.")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            return ToolResult(
                tool=self.name,
                output=f"Copied {self._rel(src)} → {self._rel(dst)}",
                metadata={"source": self._rel(src), "destination": self._rel(dst)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _mkdir(self, path: Path) -> ToolResult:
        if path.exists():
            return ToolResult(
                tool=self.name,
                output=f"Directory already exists: {self._rel(path)}",
                metadata={"path": self._rel(path), "created": False},
            )
        try:
            path.mkdir(parents=True, exist_ok=True)
            return ToolResult(
                tool=self.name,
                output=f"Created directory {self._rel(path)}",
                metadata={"path": self._rel(path), "created": True},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _stat(self, path: Path) -> ToolResult:
        if not path.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Not found: {self._rel(path)}")
        try:
            st = path.stat()
            return ToolResult(
                tool=self.name,
                output={
                    "path": self._rel(path),
                    "type": "dir" if path.is_dir() else "file",
                    "size": st.st_size,
                    "modified": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_mtime)
                    ),
                    "created": time.strftime(
                        "%Y-%m-%dT%H:%M:%SZ", time.gmtime(st.st_ctime)
                    ),
                },
                metadata={"path": self._rel(path)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))

    def _search(self, search_root: Path, pattern: str) -> ToolResult:
        if not search_root.exists():
            return ToolResult(tool=self.name, output=None,
                              error=f"Not found: {self._rel(search_root)}")
        base = search_root if search_root.is_dir() else search_root.parent
        try:
            matches = []
            for p in sorted(base.rglob("*")):
                if fnmatch.fnmatch(p.name, pattern) and self._is_allowed(p):
                    matches.append({
                        "path": self._rel(p),
                        "type": "dir" if p.is_dir() else "file",
                        "size": p.stat().st_size if p.is_file() else None,
                    })
            return ToolResult(
                tool=self.name,
                output=matches,
                metadata={"root": self._rel(base), "pattern": pattern, "count": len(matches)},
            )
        except OSError as exc:
            return ToolResult(tool=self.name, output=None, error=str(exc))
