"""Unit tests for neuralcleave.hub.registry — HubRegistry."""

from __future__ import annotations

import json

import pytest

from neuralcleave.hub.package import HubPackage
from neuralcleave.hub.registry import HubRegistry


def make_pkg(name: str = "test-skill", **kw) -> HubPackage:
    defaults = {
        "name": name,
        "version": "1.0.0",
        "description": "Test skill",
        "author": "Bob",
        "source_url": "https://example.com/test.py",
        "install_date": "2026-07-14T00:00:00Z",
    }
    return HubPackage(**{**defaults, **kw})


@pytest.fixture()
def reg(tmp_path):
    return HubRegistry(registry_file=tmp_path / "registry.json")


# ---------------------------------------------------------------------------
# Lazy load — empty registry
# ---------------------------------------------------------------------------


def test_empty_registry_list(reg):
    assert reg.list_packages() == []


def test_empty_registry_count(reg):
    assert reg.package_count() == 0


def test_get_missing_returns_none(reg):
    assert reg.get("nonexistent") is None


def test_search_empty_returns_empty(reg):
    assert reg.search("query") == []


# ---------------------------------------------------------------------------
# Add
# ---------------------------------------------------------------------------


def test_add_then_list(reg):
    pkg = make_pkg("skill-a")
    reg.add(pkg)
    pkgs = reg.list_packages()
    assert len(pkgs) == 1
    assert pkgs[0].name == "skill-a"


def test_add_increments_count(reg):
    reg.add(make_pkg("a"))
    reg.add(make_pkg("b"))
    assert reg.package_count() == 2


def test_add_replaces_existing(reg):
    reg.add(make_pkg("skill", version="1.0.0"))
    reg.add(make_pkg("skill", version="2.0.0"))
    assert reg.get("skill").version == "2.0.0"
    assert reg.package_count() == 1


def test_add_persists_to_disk(tmp_path):
    path = tmp_path / "reg.json"
    reg = HubRegistry(registry_file=path)
    reg.add(make_pkg("persisted"))
    raw = json.loads(path.read_text())
    assert any(p["name"] == "persisted" for p in raw)


# ---------------------------------------------------------------------------
# Get
# ---------------------------------------------------------------------------


def test_get_existing(reg):
    reg.add(make_pkg("find-me"))
    pkg = reg.get("find-me")
    assert pkg is not None
    assert pkg.name == "find-me"


# ---------------------------------------------------------------------------
# Remove
# ---------------------------------------------------------------------------


def test_remove_existing(reg):
    reg.add(make_pkg("to-remove"))
    reg.remove("to-remove")
    assert reg.get("to-remove") is None
    assert reg.package_count() == 0


def test_remove_missing_raises_key_error(reg):
    with pytest.raises(KeyError):
        reg.remove("no-such-package")


def test_remove_persists_deletion(tmp_path):
    path = tmp_path / "reg.json"
    reg = HubRegistry(registry_file=path)
    reg.add(make_pkg("gone"))
    reg.remove("gone")
    raw = json.loads(path.read_text())
    assert raw == []


# ---------------------------------------------------------------------------
# Enable / Disable
# ---------------------------------------------------------------------------


def test_enable(reg):
    reg.add(make_pkg("skill", enabled=False))
    reg.enable("skill")
    assert reg.get("skill").enabled is True


def test_disable(reg):
    reg.add(make_pkg("skill", enabled=True))
    reg.disable("skill")
    assert reg.get("skill").enabled is False


def test_enable_missing_raises(reg):
    with pytest.raises(KeyError):
        reg.enable("ghost")


def test_disable_missing_raises(reg):
    with pytest.raises(KeyError):
        reg.disable("ghost")


def test_enable_persisted(tmp_path):
    path = tmp_path / "reg.json"
    reg = HubRegistry(registry_file=path)
    reg.add(make_pkg("toggled", enabled=False))
    reg.enable("toggled")
    raw = json.loads(path.read_text())
    assert raw[0]["enabled"] is True


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def test_search_by_name(reg):
    reg.add(make_pkg("translate-skill"))
    reg.add(make_pkg("weather-skill"))
    results = reg.search("translate")
    assert len(results) == 1
    assert results[0].name == "translate-skill"


def test_search_by_description(reg):
    reg.add(make_pkg("skill-a", description="translates text"))
    reg.add(make_pkg("skill-b", description="forecast weather"))
    results = reg.search("translates")
    assert len(results) == 1


def test_search_by_tag(reg):
    reg.add(make_pkg("nlp-skill", tags=["nlp", "text"]))
    reg.add(make_pkg("math-skill", tags=["math"]))
    results = reg.search("nlp")
    assert len(results) == 1


def test_search_by_author(reg):
    reg.add(make_pkg("skill-alice", author="Alice"))
    reg.add(make_pkg("skill-bob", author="Bob"))
    results = reg.search("alice")
    assert len(results) == 1
    assert results[0].name == "skill-alice"


def test_search_empty_query_returns_all(reg):
    reg.add(make_pkg("a"))
    reg.add(make_pkg("b"))
    results = reg.search("")
    assert len(results) == 2


def test_search_case_insensitive(reg):
    reg.add(make_pkg("CamelSkill"))
    results = reg.search("camel")
    assert len(results) == 1


def test_search_no_match_returns_empty(reg):
    reg.add(make_pkg("skill-x"))
    assert reg.search("zzz") == []


# ---------------------------------------------------------------------------
# Persistence — load from existing file
# ---------------------------------------------------------------------------


def test_load_from_existing_file(tmp_path):
    path = tmp_path / "reg.json"
    payload = [make_pkg("preloaded").to_dict()]
    path.write_text(json.dumps(payload))

    reg = HubRegistry(registry_file=path)
    assert reg.get("preloaded") is not None
    assert reg.package_count() == 1


def test_load_invalid_json_starts_empty(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text("not json {{{")

    reg = HubRegistry(registry_file=path)
    assert reg.list_packages() == []


def test_load_non_list_json_starts_empty(tmp_path):
    path = tmp_path / "reg.json"
    path.write_text('{"key": "value"}')

    reg = HubRegistry(registry_file=path)
    assert reg.list_packages() == []


def test_missing_file_starts_empty(tmp_path):
    reg = HubRegistry(registry_file=tmp_path / "absent.json")
    assert reg.list_packages() == []
