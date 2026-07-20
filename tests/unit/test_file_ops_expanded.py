"""Tests for the expanded FileOpsTool — all 10 operations + allowed_paths."""

from __future__ import annotations

import pytest

from neuralcleave.tools.file_ops import DEFAULT_ROOT, FileOpsTool

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def tool(tmp_path):
    return FileOpsTool(root=tmp_path)


@pytest.fixture()
def tool_with_extra(tmp_path, tmp_path_factory):
    extra = tmp_path_factory.mktemp("extra")
    return FileOpsTool(root=tmp_path, allowed_paths=[extra]), tmp_path, extra


# ---------------------------------------------------------------------------
# DEFAULT_ROOT
# ---------------------------------------------------------------------------


def test_default_root_is_NeuralCleave_files() -> None:
    assert DEFAULT_ROOT.name == "NeuralCleave_files"


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_tool_creates_root_if_missing(tmp_path) -> None:
    root = tmp_path / "newdir"
    assert not root.exists()
    FileOpsTool(root=root)
    assert root.exists()


def test_tool_accepts_allowed_paths(tmp_path, tmp_path_factory) -> None:
    extra = tmp_path_factory.mktemp("extra")
    t = FileOpsTool(root=tmp_path, allowed_paths=[extra])
    assert len(t._allowed_roots) == 2


def test_tool_deduplicates_allowed_paths(tmp_path) -> None:
    t = FileOpsTool(root=tmp_path, allowed_paths=[tmp_path])
    assert len(t._allowed_roots) == 1


def test_tool_expands_tilde_in_allowed_paths(tmp_path) -> None:
    t = FileOpsTool(root=tmp_path, allowed_paths=["~"])
    assert any(str(r) != "~" for r in t._allowed_roots)


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------


def test_resolve_relative_path(tool, tmp_path) -> None:
    p = tool._resolve("foo.txt")
    assert p == tmp_path / "foo.txt"


def test_resolve_rejects_traversal(tool) -> None:
    with pytest.raises(ValueError, match="outside"):
        tool._resolve("../escape.txt")


def test_resolve_rejects_double_dot(tool) -> None:
    with pytest.raises(ValueError, match="outside"):
        tool._resolve("a/../../secret")


def test_resolve_absolute_within_root(tool, tmp_path) -> None:
    # Absolute path that IS within root should be accepted
    p = tool._resolve(str(tmp_path / "sub" / "file.txt"))
    assert p == tmp_path / "sub" / "file.txt"


def test_resolve_absolute_outside_root_rejected(tool, tmp_path) -> None:
    outside = tmp_path.parent / "outside.txt"
    with pytest.raises(ValueError, match="outside"):
        tool._resolve(str(outside))


def test_resolve_absolute_in_allowed_path(tool_with_extra) -> None:
    t, root, extra = tool_with_extra
    p = t._resolve(str(extra / "file.txt"))
    assert p == extra / "file.txt"


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_read_existing_file(tool, tmp_path) -> None:
    f = tmp_path / "hello.txt"
    f.write_text("world", encoding="utf-8")
    result = await tool.execute(operation="read", path="hello.txt")
    assert result.output == "world"
    assert result.error is None


@pytest.mark.asyncio
async def test_read_missing_file_returns_error(tool) -> None:
    result = await tool.execute(operation="read", path="missing.txt")
    assert result.error is not None
    assert result.output is None


@pytest.mark.asyncio
async def test_read_directory_returns_error(tool, tmp_path) -> None:
    (tmp_path / "subdir").mkdir()
    result = await tool.execute(operation="read", path="subdir")
    assert result.error is not None


@pytest.mark.asyncio
async def test_read_metadata_contains_path_and_size(tool, tmp_path) -> None:
    f = tmp_path / "data.txt"
    f.write_text("abc", encoding="utf-8")
    result = await tool.execute(operation="read", path="data.txt")
    assert "path" in result.metadata
    assert result.metadata["size"] == 3


@pytest.mark.asyncio
async def test_read_truncates_at_512kb(tool, tmp_path) -> None:
    big = tmp_path / "big.bin"
    big.write_bytes(b"X" * (600 * 1024))
    result = await tool.execute(operation="read", path="big.bin")
    assert len(result.output) == 512 * 1024
    assert result.metadata["truncated"] is True


@pytest.mark.asyncio
async def test_read_not_truncated_flag(tool, tmp_path) -> None:
    (tmp_path / "small.txt").write_text("hi", encoding="utf-8")
    result = await tool.execute(operation="read", path="small.txt")
    assert result.metadata["truncated"] is False


# ---------------------------------------------------------------------------
# write
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_write_creates_file(tool, tmp_path) -> None:
    result = await tool.execute(operation="write", path="new.txt", content="hello")
    assert result.error is None
    assert (tmp_path / "new.txt").read_text() == "hello"


@pytest.mark.asyncio
async def test_write_overwrites_existing(tool, tmp_path) -> None:
    (tmp_path / "x.txt").write_text("old")
    await tool.execute(operation="write", path="x.txt", content="new")
    assert (tmp_path / "x.txt").read_text() == "new"


@pytest.mark.asyncio
async def test_write_creates_parent_dirs(tool, tmp_path) -> None:
    result = await tool.execute(operation="write", path="a/b/c.txt", content="deep")
    assert result.error is None
    assert (tmp_path / "a" / "b" / "c.txt").exists()


@pytest.mark.asyncio
async def test_write_metadata_size(tool) -> None:
    result = await tool.execute(operation="write", path="w.txt", content="12345")
    assert result.metadata["size"] == 5


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_append_creates_file(tool, tmp_path) -> None:
    result = await tool.execute(operation="append", path="new.txt", content="line1\n")
    assert result.error is None
    assert (tmp_path / "new.txt").read_text() == "line1\n"


@pytest.mark.asyncio
async def test_append_adds_to_existing(tool, tmp_path) -> None:
    (tmp_path / "log.txt").write_text("first\n")
    await tool.execute(operation="append", path="log.txt", content="second\n")
    assert (tmp_path / "log.txt").read_text() == "first\nsecond\n"


@pytest.mark.asyncio
async def test_append_metadata_appended_count(tool) -> None:
    result = await tool.execute(operation="append", path="f.txt", content="abc")
    assert result.metadata["appended"] == 3


@pytest.mark.asyncio
async def test_append_creates_parent_dirs(tool, tmp_path) -> None:
    result = await tool.execute(operation="append", path="sub/log.txt", content="x")
    assert result.error is None


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_empty_directory(tool, tmp_path) -> None:
    result = await tool.execute(operation="list", path=".")
    assert result.error is None
    assert isinstance(result.output, list)
    assert result.output == []


@pytest.mark.asyncio
async def test_list_shows_files_and_dirs(tool, tmp_path) -> None:
    (tmp_path / "a.txt").write_text("x")
    (tmp_path / "sub").mkdir()
    result = await tool.execute(operation="list", path=".")
    names = {e["name"] for e in result.output}
    assert "a.txt" in names
    assert "sub" in names


@pytest.mark.asyncio
async def test_list_type_field(tool, tmp_path) -> None:
    (tmp_path / "f.txt").write_text("")
    (tmp_path / "d").mkdir()
    result = await tool.execute(operation="list", path=".")
    types = {e["name"]: e["type"] for e in result.output}
    assert types["f.txt"] == "file"
    assert types["d"] == "dir"


@pytest.mark.asyncio
async def test_list_size_is_none_for_dirs(tool, tmp_path) -> None:
    (tmp_path / "d").mkdir()
    result = await tool.execute(operation="list", path=".")
    dirs = [e for e in result.output if e["type"] == "dir"]
    assert all(e["size"] is None for e in dirs)


@pytest.mark.asyncio
async def test_list_missing_directory_returns_error(tool) -> None:
    result = await tool.execute(operation="list", path="ghost/")
    assert result.error is not None


@pytest.mark.asyncio
async def test_list_metadata_count(tool, tmp_path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("")
    result = await tool.execute(operation="list", path=".")
    assert result.metadata["count"] == 3


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_existing_file(tool, tmp_path) -> None:
    f = tmp_path / "del.txt"
    f.write_text("bye")
    result = await tool.execute(operation="delete", path="del.txt")
    assert result.error is None
    assert not f.exists()


@pytest.mark.asyncio
async def test_delete_missing_file_returns_error(tool) -> None:
    result = await tool.execute(operation="delete", path="ghost.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_delete_directory_returns_error(tool, tmp_path) -> None:
    (tmp_path / "d").mkdir()
    result = await tool.execute(operation="delete", path="d")
    assert result.error is not None


# ---------------------------------------------------------------------------
# move
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_move_file(tool, tmp_path) -> None:
    (tmp_path / "src.txt").write_text("content")
    result = await tool.execute(operation="move", path="src.txt", destination="dst.txt")
    assert result.error is None
    assert not (tmp_path / "src.txt").exists()
    assert (tmp_path / "dst.txt").read_text() == "content"


@pytest.mark.asyncio
async def test_move_missing_source_returns_error(tool) -> None:
    result = await tool.execute(operation="move", path="ghost.txt", destination="dst.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_move_no_destination_returns_error(tool) -> None:
    result = await tool.execute(operation="move", path="src.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_move_creates_parent_dir(tool, tmp_path) -> None:
    (tmp_path / "src.txt").write_text("x")
    result = await tool.execute(operation="move", path="src.txt", destination="sub/dst.txt")
    assert result.error is None
    assert (tmp_path / "sub" / "dst.txt").exists()


@pytest.mark.asyncio
async def test_move_metadata(tool, tmp_path) -> None:
    (tmp_path / "f.txt").write_text("")
    result = await tool.execute(operation="move", path="f.txt", destination="g.txt")
    assert "source" in result.metadata
    assert "destination" in result.metadata


# ---------------------------------------------------------------------------
# copy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_copy_file(tool, tmp_path) -> None:
    (tmp_path / "orig.txt").write_text("data")
    result = await tool.execute(operation="copy", path="orig.txt", destination="copy.txt")
    assert result.error is None
    assert (tmp_path / "orig.txt").exists()
    assert (tmp_path / "copy.txt").read_text() == "data"


@pytest.mark.asyncio
async def test_copy_missing_source_returns_error(tool) -> None:
    result = await tool.execute(operation="copy", path="ghost.txt", destination="dst.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_copy_directory_returns_error(tool, tmp_path) -> None:
    (tmp_path / "d").mkdir()
    result = await tool.execute(operation="copy", path="d", destination="d2")
    assert result.error is not None


@pytest.mark.asyncio
async def test_copy_no_destination_returns_error(tool) -> None:
    result = await tool.execute(operation="copy", path="f.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_copy_creates_parent_dir(tool, tmp_path) -> None:
    (tmp_path / "src.txt").write_text("x")
    result = await tool.execute(operation="copy", path="src.txt", destination="sub/copy.txt")
    assert result.error is None
    assert (tmp_path / "sub" / "copy.txt").exists()


# ---------------------------------------------------------------------------
# mkdir
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mkdir_creates_directory(tool, tmp_path) -> None:
    result = await tool.execute(operation="mkdir", path="new_dir")
    assert result.error is None
    assert (tmp_path / "new_dir").is_dir()


@pytest.mark.asyncio
async def test_mkdir_creates_nested(tool, tmp_path) -> None:
    result = await tool.execute(operation="mkdir", path="a/b/c")
    assert result.error is None
    assert (tmp_path / "a" / "b" / "c").is_dir()


@pytest.mark.asyncio
async def test_mkdir_already_exists(tool, tmp_path) -> None:
    (tmp_path / "existing").mkdir()
    result = await tool.execute(operation="mkdir", path="existing")
    assert result.error is None
    assert result.metadata["created"] is False


@pytest.mark.asyncio
async def test_mkdir_new_created_flag(tool) -> None:
    result = await tool.execute(operation="mkdir", path="brand_new")
    assert result.metadata["created"] is True


# ---------------------------------------------------------------------------
# stat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stat_file(tool, tmp_path) -> None:
    f = tmp_path / "s.txt"
    f.write_text("hello")
    result = await tool.execute(operation="stat", path="s.txt")
    assert result.error is None
    out = result.output
    assert out["type"] == "file"
    assert out["size"] == 5
    assert "modified" in out
    assert "created" in out


@pytest.mark.asyncio
async def test_stat_directory(tool, tmp_path) -> None:
    (tmp_path / "d").mkdir()
    result = await tool.execute(operation="stat", path="d")
    assert result.output["type"] == "dir"


@pytest.mark.asyncio
async def test_stat_missing_returns_error(tool) -> None:
    result = await tool.execute(operation="stat", path="ghost.txt")
    assert result.error is not None


@pytest.mark.asyncio
async def test_stat_modified_iso_format(tool, tmp_path) -> None:
    (tmp_path / "t.txt").write_text("")
    result = await tool.execute(operation="stat", path="t.txt")
    mod = result.output["modified"]
    assert "T" in mod and "Z" in mod


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_finds_matching_files(tool, tmp_path) -> None:
    (tmp_path / "a.md").write_text("")
    (tmp_path / "b.py").write_text("")
    result = await tool.execute(operation="search", path=".", pattern="*.md")
    assert result.error is None
    names = [e["path"] for e in result.output]
    assert any("a.md" in n for n in names)
    assert all("b.py" not in n for n in names)


@pytest.mark.asyncio
async def test_search_star_matches_all(tool, tmp_path) -> None:
    (tmp_path / "x.txt").write_text("")
    (tmp_path / "y.py").write_text("")
    result = await tool.execute(operation="search", path=".", pattern="*")
    assert result.metadata["count"] >= 2


@pytest.mark.asyncio
async def test_search_nested(tool, tmp_path) -> None:
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "deep.md").write_text("")
    result = await tool.execute(operation="search", path=".", pattern="*.md")
    names = [e["path"] for e in result.output]
    assert any("deep.md" in n for n in names)


@pytest.mark.asyncio
async def test_search_missing_root_returns_error(tool) -> None:
    result = await tool.execute(operation="search", path="ghost", pattern="*")
    assert result.error is not None


@pytest.mark.asyncio
async def test_search_metadata_count(tool, tmp_path) -> None:
    for i in range(3):
        (tmp_path / f"f{i}.txt").write_text("")
    result = await tool.execute(operation="search", path=".", pattern="*.txt")
    assert result.metadata["count"] == 3


@pytest.mark.asyncio
async def test_search_metadata_pattern(tool, tmp_path) -> None:
    result = await tool.execute(operation="search", path=".", pattern="*.log")
    assert result.metadata["pattern"] == "*.log"


# ---------------------------------------------------------------------------
# Unknown operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_operation_returns_error(tool) -> None:
    result = await tool.execute(operation="explode", path=".")
    assert result.error is not None
    assert "explode" in result.error


# ---------------------------------------------------------------------------
# allowed_paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_path_read(tool_with_extra) -> None:
    t, root, extra = tool_with_extra
    (extra / "remote.txt").write_text("remote content")
    result = await t.execute(operation="read", path=str(extra / "remote.txt"))
    assert result.error is None
    assert result.output == "remote content"


@pytest.mark.asyncio
async def test_allowed_path_write(tool_with_extra) -> None:
    t, root, extra = tool_with_extra
    result = await t.execute(
        operation="write",
        path=str(extra / "out.txt"),
        content="written",
    )
    assert result.error is None
    assert (extra / "out.txt").read_text() == "written"


@pytest.mark.asyncio
async def test_allowed_path_list(tool_with_extra) -> None:
    t, root, extra = tool_with_extra
    (extra / "item.txt").write_text("")
    result = await t.execute(operation="list", path=str(extra))
    assert result.error is None
    names = [e["name"] for e in result.output]
    assert "item.txt" in names


@pytest.mark.asyncio
async def test_disallowed_absolute_path_rejected(tool, tmp_path) -> None:
    outside = tmp_path.parent / "outside.txt"
    result = await tool.execute(operation="read", path=str(outside))
    assert result.error is not None


@pytest.mark.asyncio
async def test_path_traversal_via_symlink_rejected(tool, tmp_path) -> None:
    # Attempt: relative path that tries to escape via ..
    result = await tool.execute(operation="read", path="../../etc/passwd")
    assert result.error is not None


# ---------------------------------------------------------------------------
# _rel helper
# ---------------------------------------------------------------------------


def test_rel_within_root(tool, tmp_path) -> None:
    p = tmp_path / "sub" / "file.txt"
    assert tool._rel(p) == "sub/file.txt" or tool._rel(p) == "sub\\file.txt"


def test_rel_outside_all_roots(tool, tmp_path) -> None:
    outside = tmp_path.parent / "nope.txt"
    rel = tool._rel(outside)
    assert str(outside) in rel or "nope.txt" in rel
