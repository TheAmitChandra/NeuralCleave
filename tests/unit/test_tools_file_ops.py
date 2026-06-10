"""Unit tests for cortexflow.tools.file_ops — FileOpsTool sandboxed operations."""

from __future__ import annotations

import pytest

from cortexflow.tools.file_ops import FileOpsTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool(tmp_path):
    return FileOpsTool(root=tmp_path)


# ---------------------------------------------------------------------------
# Write + Read round trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_and_read_round_trip(tool):
    write_result = await tool.execute(operation="write", path="hello.txt", content="world")
    assert write_result.success

    read_result = await tool.execute(operation="read", path="hello.txt")
    assert read_result.success
    assert read_result.output == "world"


@pytest.mark.asyncio
async def test_write_creates_parent_directories(tool):
    result = await tool.execute(operation="write", path="deep/sub/file.txt", content="nested")
    assert result.success


@pytest.mark.asyncio
async def test_write_returns_metadata_with_size(tool):
    result = await tool.execute(operation="write", path="meta.txt", content="1234567890")
    assert result.success
    assert result.metadata["size"] == 10


# ---------------------------------------------------------------------------
# Read edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_nonexistent_returns_error(tool):
    result = await tool.execute(operation="read", path="nope.txt")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_read_directory_suggests_list(tool, tmp_path):
    (tmp_path / "subdir").mkdir()
    result = await tool.execute(operation="read", path="subdir")
    assert not result.success
    assert "list" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_read_returns_metadata(tool):
    await tool.execute(operation="write", path="r.txt", content="abc")
    result = await tool.execute(operation="read", path="r.txt")
    assert result.success
    assert "path" in result.metadata
    assert result.metadata["size"] == 3


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty_root(tool):
    result = await tool.execute(operation="list", path=".")
    assert result.success
    assert isinstance(result.output, list)


@pytest.mark.asyncio
async def test_list_shows_written_file(tool):
    await tool.execute(operation="write", path="listed.txt", content="x")
    result = await tool.execute(operation="list", path=".")
    assert result.success
    names = [e["name"] for e in result.output]
    assert "listed.txt" in names


@pytest.mark.asyncio
async def test_list_distinguishes_files_and_dirs(tool, tmp_path):
    (tmp_path / "adir").mkdir()
    await tool.execute(operation="write", path="afile.txt", content="")
    result = await tool.execute(operation="list", path=".")
    assert result.success
    types = {e["name"]: e["type"] for e in result.output}
    assert types.get("adir") == "dir"
    assert types.get("afile.txt") == "file"


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_file(tool):
    await tool.execute(operation="write", path="todelete.txt", content="bye")
    result = await tool.execute(operation="delete", path="todelete.txt")
    assert result.success

    read_after = await tool.execute(operation="read", path="todelete.txt")
    assert not read_after.success


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_error(tool):
    result = await tool.execute(operation="delete", path="ghost.txt")
    assert not result.success


@pytest.mark.asyncio
async def test_delete_directory_returns_error(tool, tmp_path):
    (tmp_path / "safedir").mkdir()
    result = await tool.execute(operation="delete", path="safedir")
    assert not result.success
    assert "directory" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_absolute_path_rejected(tool):
    result = await tool.execute(operation="read", path="/etc/passwd")
    assert not result.success
    assert result.error is not None


@pytest.mark.asyncio
async def test_path_traversal_rejected(tool):
    result = await tool.execute(operation="read", path="../../etc/passwd")
    assert not result.success
    assert result.error is not None


# ---------------------------------------------------------------------------
# Unknown operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_operation_returns_error(tool):
    result = await tool.execute(operation="frobnicate", path="x.txt")
    assert not result.success
    assert "Unknown operation" in (result.error or "")
