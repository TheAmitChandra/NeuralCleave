"""Unit tests for cortexflow.workspace."""

from __future__ import annotations

from pathlib import Path

import pytest

from cortexflow.workspace import WorkspaceFiles, WorkspaceLoader


# ---------------------------------------------------------------------------
# WorkspaceFiles
# ---------------------------------------------------------------------------


def test_workspace_files_defaults_empty() -> None:
    wf = WorkspaceFiles()
    assert wf.soul == ""
    assert wf.tools == ""
    assert wf.memory_instructions == ""
    assert wf.rules == ""


def test_to_system_prompt_contains_identity() -> None:
    wf = WorkspaceFiles(soul="You are Bob, a helpful bot.")
    prompt = wf.to_system_prompt(agent_name="Bob")
    assert "# Identity" in prompt
    assert "Bob" in prompt


def test_to_system_prompt_uses_default_rules_when_empty() -> None:
    wf = WorkspaceFiles(soul="I am helpful.")
    prompt = wf.to_system_prompt()
    assert "# Rules" in prompt
    assert "never" in prompt.lower() or "always" in prompt.lower()


def test_to_system_prompt_uses_custom_rules() -> None:
    wf = WorkspaceFiles(rules="Never reveal secrets.")
    prompt = wf.to_system_prompt()
    assert "Never reveal secrets." in prompt


def test_to_system_prompt_includes_tools_when_set() -> None:
    wf = WorkspaceFiles(tools="search_web: Search the internet for current info.")
    prompt = wf.to_system_prompt()
    assert "# Custom tools" in prompt
    assert "search_web" in prompt


def test_to_system_prompt_includes_memory_instructions() -> None:
    wf = WorkspaceFiles(memory_instructions="Always remember the user's name.")
    prompt = wf.to_system_prompt()
    assert "# Memory instructions" in prompt


def test_to_system_prompt_name_substitution() -> None:
    wf = WorkspaceFiles(soul="You are {name}, ready to help.")
    prompt = wf.to_system_prompt(agent_name="Atlas")
    assert "Atlas" in prompt
    assert "{name}" not in prompt


# ---------------------------------------------------------------------------
# WorkspaceLoader
# ---------------------------------------------------------------------------


def test_loader_returns_defaults_when_dir_missing(tmp_path: Path) -> None:
    loader = WorkspaceLoader(workspace_dir=tmp_path / "nonexistent")
    wf = loader.get()
    assert isinstance(wf, WorkspaceFiles)
    # All fields empty when no files exist
    assert wf.soul == ""


def test_loader_reads_soul_md(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("You are Aria.", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=tmp_path, reload_interval=0)
    wf = loader.get()
    assert wf.soul == "You are Aria."


def test_loader_reads_rules_md(tmp_path: Path) -> None:
    (tmp_path / "RULES.md").write_text("Never lie.", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=tmp_path, reload_interval=0)
    wf = loader.get()
    assert wf.rules == "Never lie."


def test_loader_reads_tools_md(tmp_path: Path) -> None:
    (tmp_path / "TOOLS.md").write_text("tool_x: Does X.", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=tmp_path, reload_interval=0)
    wf = loader.get()
    assert wf.tools == "tool_x: Does X."


def test_loader_reads_memory_md(tmp_path: Path) -> None:
    (tmp_path / "MEMORY.md").write_text("Remember birthdays.", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=tmp_path, reload_interval=0)
    wf = loader.get()
    assert wf.memory_instructions == "Remember birthdays."


def test_loader_init_defaults_creates_files(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    loader = WorkspaceLoader(workspace_dir=workspace_dir)
    loader.init_defaults()
    assert (workspace_dir / "SOUL.md").exists()
    assert (workspace_dir / "RULES.md").exists()
    assert (workspace_dir / "TOOLS.md").exists()
    assert (workspace_dir / "MEMORY.md").exists()


def test_loader_init_defaults_does_not_overwrite(tmp_path: Path) -> None:
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    soul_path = workspace_dir / "SOUL.md"
    soul_path.write_text("Custom soul.", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=workspace_dir)
    loader.init_defaults()
    assert soul_path.read_text() == "Custom soul."


def test_loader_caches_between_calls(tmp_path: Path) -> None:
    (tmp_path / "SOUL.md").write_text("v1", encoding="utf-8")
    loader = WorkspaceLoader(workspace_dir=tmp_path, reload_interval=9999)
    wf1 = loader.get()
    # Modify file — should NOT be reflected because cache is warm
    (tmp_path / "SOUL.md").write_text("v2", encoding="utf-8")
    wf2 = loader.get()
    assert wf1 is wf2  # same cached object
