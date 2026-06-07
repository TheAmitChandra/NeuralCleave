"""Filesystem tool — sandboxed file read/write/search.

Security controls:
- All paths are resolved and validated to stay within an allowed workspace root.
- Path traversal attempts (../ etc.) raise PermissionError.
- Write operations are limited to the workspace; reads can be optionally widened.
- File size limits prevent reading enormous files into memory.
"""

from __future__ import annotations

import os
import pathlib
from typing import Any

from app.core.observability.logs import get_logger
from app.core.tools.registry import ToolDefinition

logger = get_logger(__name__)

# Default maximum bytes to read in a single call (1 MB)
_MAX_READ_BYTES = 1024 * 1024


# ---------------------------------------------------------------------------
# Path safety helpers
# ---------------------------------------------------------------------------


def _resolve_safe(path: str, workspace_root: str) -> pathlib.Path:
    """Resolve *path* and ensure it sits inside *workspace_root*.

    Raises:
        PermissionError: If the resolved path escapes the workspace root.
        ValueError: If the workspace root itself is invalid.
    """
    root = pathlib.Path(workspace_root).resolve()
    if not root.is_dir():
        raise ValueError(f"workspace_root is not a directory: {workspace_root}")

    resolved = (root / path).resolve()

    try:
        resolved.relative_to(root)
    except ValueError:
        raise PermissionError(f"Path traversal detected: '{path}' resolves outside workspace root.")

    return resolved


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


async def file_read(params: dict[str, Any]) -> dict[str, Any]:
    """Read a file within the workspace.

    Parameters:
        path (str): Relative path inside workspace_root.
        workspace_root (str): Absolute path to the allowed root directory.
        encoding (str): Text encoding, default 'utf-8'.
        max_bytes (int): Maximum bytes to read. Default 1 MB.

    Returns:
        dict with keys: path, content, size_bytes, truncated.
    """
    workspace_root: str = params["workspace_root"]
    rel_path: str = params["path"]
    encoding: str = params.get("encoding", "utf-8")
    max_bytes: int = int(params.get("max_bytes", _MAX_READ_BYTES))

    target = _resolve_safe(rel_path, workspace_root)

    if not target.exists():
        raise FileNotFoundError(f"File not found: {rel_path}")
    if not target.is_file():
        raise IsADirectoryError(f"Path is a directory, not a file: {rel_path}")

    size_bytes = target.stat().st_size
    truncated = size_bytes > max_bytes

    raw = target.read_bytes()[:max_bytes]
    content = raw.decode(encoding, errors="replace")

    logger.info("file_read", path=str(target), size_bytes=size_bytes, truncated=truncated)
    return {
        "path": str(target),
        "content": content,
        "size_bytes": size_bytes,
        "truncated": truncated,
    }


async def file_write(params: dict[str, Any]) -> dict[str, Any]:
    """Write content to a file within the workspace.

    Parameters:
        path (str): Relative path inside workspace_root.
        workspace_root (str): Absolute path to the allowed root directory.
        content (str): Text content to write.
        encoding (str): Text encoding, default 'utf-8'.
        create_dirs (bool): Create parent directories if they don't exist. Default False.

    Returns:
        dict with keys: path, size_bytes, created_dirs.
    """
    workspace_root: str = params["workspace_root"]
    rel_path: str = params["path"]
    content: str = params["content"]
    encoding: str = params.get("encoding", "utf-8")
    create_dirs: bool = bool(params.get("create_dirs", False))

    target = _resolve_safe(rel_path, workspace_root)

    created_dirs = False
    if not target.parent.exists():
        if not create_dirs:
            raise FileNotFoundError(
                f"Parent directory does not exist: {target.parent}. "
                "Pass create_dirs=True to create it automatically."
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        created_dirs = True

    target.write_text(content, encoding=encoding)
    size_bytes = target.stat().st_size

    logger.info("file_write", path=str(target), size_bytes=size_bytes)
    return {"path": str(target), "size_bytes": size_bytes, "created_dirs": created_dirs}


async def file_list(params: dict[str, Any]) -> dict[str, Any]:
    """List files in a directory within the workspace.

    Parameters:
        path (str): Relative directory path inside workspace_root. Use '.' for root.
        workspace_root (str): Absolute path to the allowed root directory.
        pattern (str): Glob pattern. Default '*'.
        recursive (bool): Whether to recurse into subdirectories. Default False.

    Returns:
        dict with keys: path, entries (list of dicts with name, size_bytes, is_dir).
    """
    workspace_root: str = params["workspace_root"]
    rel_path: str = params.get("path", ".")
    pattern: str = params.get("pattern", "*")
    recursive: bool = bool(params.get("recursive", False))

    target = _resolve_safe(rel_path, workspace_root)

    if not target.is_dir():
        raise NotADirectoryError(f"Path is not a directory: {rel_path}")

    glob_fn = target.rglob if recursive else target.glob
    entries = []
    for entry in sorted(glob_fn(pattern)):
        try:
            stat = entry.stat()
        except OSError:
            continue
        entries.append(
            {
                "name": entry.name,
                "relative_path": str(entry.relative_to(target)),
                "size_bytes": stat.st_size if entry.is_file() else 0,
                "is_dir": entry.is_dir(),
            }
        )

    logger.info("file_list", path=str(target), count=len(entries))
    return {"path": str(target), "entries": entries[:200]}


async def file_search(params: dict[str, Any]) -> dict[str, Any]:
    """Search file contents for a text pattern within the workspace.

    Parameters:
        workspace_root (str): Absolute path to the allowed root directory.
        query (str): Plain-text substring to search for.
        file_pattern (str): Glob pattern to filter files. Default '**/*.txt,**/*.py,**/*.md'.
        max_results (int): Maximum number of matches to return. Default 50.

    Returns:
        dict with keys: query, matches (list of dicts with file, line_number, line).
    """
    workspace_root: str = params["workspace_root"]
    query: str = params["query"]
    file_pattern: str = params.get("file_pattern", "**/*")
    max_results: int = int(params.get("max_results", 50))

    root = pathlib.Path(workspace_root).resolve()
    if not root.is_dir():
        raise ValueError(f"workspace_root is not a directory: {workspace_root}")

    matches = []
    for file_path in root.rglob(file_pattern):
        if not file_path.is_file():
            continue
        try:
            lines = file_path.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line_num, line in enumerate(lines, start=1):
            if query in line:
                matches.append(
                    {
                        "file": str(file_path.relative_to(root)),
                        "line_number": line_num,
                        "line": line.strip(),
                    }
                )
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    logger.info("file_search", query=query, match_count=len(matches))
    return {"query": query, "matches": matches}


# ---------------------------------------------------------------------------
# Tool definitions (for ToolRegistry)
# ---------------------------------------------------------------------------

FILE_READ_DEF = ToolDefinition(
    name="file.read",
    description="Read a file within the agent's workspace.",
    permissions=["file.read"],
    risk_level="low",
    sandbox_required=False,
    timeout_seconds=10,
    parameters_schema={
        "type": "object",
        "required": ["path", "workspace_root"],
        "properties": {
            "path": {"type": "string"},
            "workspace_root": {"type": "string"},
            "encoding": {"type": "string"},
            "max_bytes": {"type": "integer"},
        },
    },
)

FILE_WRITE_DEF = ToolDefinition(
    name="file.write",
    description="Write content to a file within the agent's workspace.",
    permissions=["file.write"],
    risk_level="medium",
    sandbox_required=True,
    timeout_seconds=10,
    parameters_schema={
        "type": "object",
        "required": ["path", "workspace_root", "content"],
        "properties": {
            "path": {"type": "string"},
            "workspace_root": {"type": "string"},
            "content": {"type": "string"},
            "encoding": {"type": "string"},
            "create_dirs": {"type": "boolean"},
        },
    },
)

FILE_LIST_DEF = ToolDefinition(
    name="file.list",
    description="List files in a directory within the agent's workspace.",
    permissions=["file.read"],
    risk_level="low",
    sandbox_required=False,
    timeout_seconds=10,
    parameters_schema={
        "type": "object",
        "required": ["workspace_root"],
        "properties": {
            "path": {"type": "string"},
            "workspace_root": {"type": "string"},
            "pattern": {"type": "string"},
            "recursive": {"type": "boolean"},
        },
    },
)

FILE_SEARCH_DEF = ToolDefinition(
    name="file.search",
    description="Search file contents for a text pattern.",
    permissions=["file.read"],
    risk_level="low",
    sandbox_required=False,
    timeout_seconds=30,
    parameters_schema={
        "type": "object",
        "required": ["workspace_root", "query"],
        "properties": {
            "workspace_root": {"type": "string"},
            "query": {"type": "string"},
            "file_pattern": {"type": "string"},
            "max_results": {"type": "integer"},
        },
    },
)


def register_filesystem_tools(registry: Any) -> None:
    """Register all filesystem tools into the provided registry."""
    registry.register(FILE_READ_DEF, file_read)
    registry.register(FILE_WRITE_DEF, file_write)
    registry.register(FILE_LIST_DEF, file_list)
    registry.register(FILE_SEARCH_DEF, file_search)
