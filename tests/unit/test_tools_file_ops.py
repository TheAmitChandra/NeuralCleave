"""Unit tests for NeuralCleave.tools.file_ops — FileOpsTool sandboxed operations."""

from __future__ import annotations

from pathlib import Path

import pytest

from neuralcleave.tools.file_ops import FileOpsTool

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


@pytest.mark.asyncio
async def test_write_oserror_returns_error(tool, monkeypatch):
    def _raise(*_a, **_k):
        raise OSError("no space left on device")

    monkeypatch.setattr(Path, "write_text", _raise)
    result = await tool.execute(operation="write", path="fail.txt", content="x")
    assert not result.success
    assert "no space left" in (result.error or "")


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


@pytest.mark.asyncio
async def test_read_oserror_returns_error(tool, monkeypatch):
    await tool.execute(operation="write", path="broken.txt", content="x")

    def _raise(*_a, **_k):
        raise OSError("disk error")

    monkeypatch.setattr(Path, "read_bytes", _raise)
    result = await tool.execute(operation="read", path="broken.txt")
    assert not result.success
    assert "disk error" in (result.error or "")


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


@pytest.mark.asyncio
async def test_list_directory_not_found_returns_error(tool):
    result = await tool.execute(operation="list", path="missingdir/missingfile.txt")
    assert not result.success
    assert "not found" in (result.error or "").lower()


@pytest.mark.asyncio
async def test_list_oserror_returns_error(tool, monkeypatch):
    def _raise(*_a, **_k):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "iterdir", _raise)
    result = await tool.execute(operation="list", path=".")
    assert not result.success
    assert "permission denied" in (result.error or "")


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


@pytest.mark.asyncio
async def test_delete_oserror_returns_error(tool, monkeypatch):
    await tool.execute(operation="write", path="locked.txt", content="x")

    def _raise(*_a, **_k):
        raise OSError("file in use")

    monkeypatch.setattr(Path, "unlink", _raise)
    result = await tool.execute(operation="delete", path="locked.txt")
    assert not result.success
    assert "file in use" in (result.error or "")


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
