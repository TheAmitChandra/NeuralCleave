"""Unit tests for NeuralCleave.hub.package — HubPackage dataclass."""

from __future__ import annotations

import pytest

from neuralcleave.hub.package import HubPackage


def make_pkg(**overrides) -> HubPackage:
    defaults = {
        "name": "my-skill",
        "version": "1.0.0",
        "description": "A test skill",
        "author": "Alice",
        "source_url": "https://example.com/my_skill.py",
        "install_date": "2026-07-14T10:00:00Z",
    }
    return HubPackage(**{**defaults, **overrides})


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_construction_defaults():
    pkg = make_pkg()
    assert pkg.name == "my-skill"
    assert pkg.version == "1.0.0"
    assert pkg.enabled is True
    assert pkg.tags == []
    assert pkg.checksum == ""
    assert pkg.license == "MIT"


def test_construction_with_tags():
    pkg = make_pkg(tags=["nlp", "text"])
    assert pkg.tags == ["nlp", "text"]


def test_construction_with_checksum():
    pkg = make_pkg(checksum="abc123")
    assert pkg.checksum == "abc123"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_empty_name_raises():
    with pytest.raises(ValueError, match="name must not be empty"):
        make_pkg(name="")


def test_invalid_name_characters_raises():
    with pytest.raises(ValueError, match="invalid characters"):
        make_pkg(name="my skill!")


def test_name_with_hyphens_valid():
    pkg = make_pkg(name="my-cool-skill")
    assert pkg.name == "my-cool-skill"


def test_name_with_underscores_valid():
    pkg = make_pkg(name="my_cool_skill")
    assert pkg.name == "my_cool_skill"


def test_name_with_digits_valid():
    pkg = make_pkg(name="skill123")
    assert pkg.name == "skill123"


def test_empty_version_raises():
    with pytest.raises(ValueError, match="version must not be empty"):
        make_pkg(version="")


# ---------------------------------------------------------------------------
# to_dict
# ---------------------------------------------------------------------------


def test_to_dict_contains_all_fields():
    pkg = make_pkg(tags=["a", "b"], checksum="deadbeef")
    d = pkg.to_dict()
    assert d["name"] == "my-skill"
    assert d["version"] == "1.0.0"
    assert d["description"] == "A test skill"
    assert d["author"] == "Alice"
    assert d["tags"] == ["a", "b"]
    assert d["enabled"] is True
    assert d["checksum"] == "deadbeef"
    assert d["license"] == "MIT"
    assert "source_url" in d
    assert "install_date" in d
    assert "homepage" in d


# ---------------------------------------------------------------------------
# from_dict
# ---------------------------------------------------------------------------


def test_from_dict_roundtrip():
    original = make_pkg(tags=["t1"], checksum="c1", enabled=False)
    restored = HubPackage.from_dict(original.to_dict())
    assert restored.name == original.name
    assert restored.version == original.version
    assert restored.tags == ["t1"]
    assert restored.checksum == "c1"
    assert restored.enabled is False


def test_from_dict_missing_optional_fields_uses_defaults():
    data = {"name": "simple", "version": "0.1.0"}
    pkg = HubPackage.from_dict(data)
    assert pkg.tags == []
    assert pkg.enabled is True
    assert pkg.checksum == ""
    assert pkg.description == ""
    assert pkg.author == ""
    assert pkg.homepage == ""
    assert pkg.license == "MIT"
