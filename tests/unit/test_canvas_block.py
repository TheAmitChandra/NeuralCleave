"""Unit tests for neuralcleave.canvas.block — CanvasBlock."""

from __future__ import annotations

import pytest

from neuralcleave.canvas.block import BLOCK_TYPES, CanvasBlock

# ---------------------------------------------------------------------------
# BLOCK_TYPES set
# ---------------------------------------------------------------------------


def test_block_types_contains_expected():
    assert "text" in BLOCK_TYPES
    assert "markdown" in BLOCK_TYPES
    assert "image" in BLOCK_TYPES
    assert "table" in BLOCK_TYPES
    assert "code" in BLOCK_TYPES
    assert "chart" in BLOCK_TYPES
    assert "html" in BLOCK_TYPES


# ---------------------------------------------------------------------------
# Construction + validation
# ---------------------------------------------------------------------------


def test_valid_construction():
    b = CanvasBlock(id="abc", block_type="text", content="hello")
    assert b.id == "abc"
    assert b.block_type == "text"
    assert b.content == "hello"
    assert b.title == ""
    assert b.created_at == ""


def test_invalid_block_type_raises():
    with pytest.raises(ValueError, match="Unknown block_type"):
        CanvasBlock(id="x", block_type="unknown", content="")


@pytest.mark.parametrize("bt", list(BLOCK_TYPES))
def test_all_valid_block_types(bt):
    b = CanvasBlock(id="x", block_type=bt, content="")
    assert b.block_type == bt


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_contains_all_fields():
    b = CanvasBlock(
        id="id1", block_type="markdown", content="**bold**",
        title="My Title", created_at="2026-07-14T10:00:00Z",
    )
    d = b.to_dict()
    assert d["id"] == "id1"
    assert d["block_type"] == "markdown"
    assert d["content"] == "**bold**"
    assert d["title"] == "My Title"
    assert d["created_at"] == "2026-07-14T10:00:00Z"


def test_to_dict_with_dict_content():
    content = {"headers": ["A", "B"], "rows": [[1, 2]]}
    b = CanvasBlock(id="t", block_type="table", content=content)
    d = b.to_dict()
    assert d["content"] == content


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------


def test_from_dict_roundtrip():
    original = CanvasBlock(
        id="r1", block_type="code", content={"code": "x=1", "language": "python"},
        title="Code", created_at="2026-07-14T00:00:00Z",
    )
    restored = CanvasBlock.from_dict(original.to_dict())
    assert restored.id == original.id
    assert restored.block_type == original.block_type
    assert restored.content == original.content
    assert restored.title == original.title


def test_from_dict_missing_optional_fields():
    b = CanvasBlock.from_dict({"id": "x", "block_type": "text", "content": "hi"})
    assert b.title == ""
    assert b.created_at == ""


def test_from_dict_missing_id_defaults_empty():
    b = CanvasBlock.from_dict({"block_type": "text", "content": "hi"})
    assert b.id == ""


# ---------------------------------------------------------------------------
# CanvasBlock.new
# ---------------------------------------------------------------------------


def test_new_generates_id():
    b = CanvasBlock.new("text", "hello")
    assert len(b.id) == 32  # UUID4 hex


def test_new_sets_created_at():
    b = CanvasBlock.new("text", "hi")
    assert "T" in b.created_at
    assert b.created_at.endswith("Z")


def test_new_unique_ids():
    b1 = CanvasBlock.new("text", "a")
    b2 = CanvasBlock.new("text", "b")
    assert b1.id != b2.id


def test_new_with_title():
    b = CanvasBlock.new("markdown", "# Hello", title="Greeting")
    assert b.title == "Greeting"


def test_new_invalid_type_raises():
    with pytest.raises(ValueError, match="Unknown block_type"):
        CanvasBlock.new("bad_type", "content")


def test_new_table_content():
    content = {"headers": ["X"], "rows": [[1]]}
    b = CanvasBlock.new("table", content)
    assert b.content == content


def test_new_chart_content():
    content = {"chart_type": "bar", "labels": ["A"], "values": [10]}
    b = CanvasBlock.new("chart", content)
    assert b.content == content
