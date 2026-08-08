"""Validate that every file in skills/examples/ has SKILL_METADATA and async run()."""
import ast
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).parent.parent / "skills" / "examples"
SKILL_FILES = sorted(EXAMPLES_DIR.glob("*.py"))


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.stem)
def test_skill_has_metadata(skill_path):
    source = skill_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigns = {
        node.targets[0].id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    }
    assert "SKILL_METADATA" in assigns, f"{skill_path.name}: missing SKILL_METADATA"


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.stem)
def test_skill_has_run_function(skill_path):
    source = skill_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    async_fns = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef)
    }
    assert "run" in async_fns, f"{skill_path.name}: missing async def run()"


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: p.stem)
def test_skill_metadata_has_required_keys(skill_path):
    source = skill_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == "SKILL_METADATA"
            and isinstance(node.value, ast.Dict)
        ):
            keys = {
                k.s if isinstance(k, ast.Constant) else None
                for k in node.value.keys
            }
            assert "name" in keys, f"{skill_path.name}: SKILL_METADATA missing 'name'"
            assert "description" in keys, f"{skill_path.name}: SKILL_METADATA missing 'description'"
            return
    pytest.fail(f"{skill_path.name}: SKILL_METADATA is not a dict literal")
