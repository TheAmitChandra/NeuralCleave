"""Tests for the `neuralcleave skills review` and `skills quarantine` CLI commands."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from neuralcleave.cli import cli
from neuralcleave.skills.review import SkillReviewQueue
from neuralcleave.skills.writer import SkillWriter

SIMPLE_CODE = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"


@pytest.fixture()
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture()
def fresh_queue():
    queue = SkillReviewQueue(db_path=None)
    with patch("neuralcleave.skills.review.REVIEW_QUEUE", queue):
        yield queue


@pytest.fixture()
def home_skills_dir(tmp_path: Path):
    """CLI commands construct a bare SkillWriter(), which resolves
    neuralcleave.skills.writer._DEFAULT_SKILLS_DIR — a module-level constant
    computed once at import time, so patching the HOME env var has no effect
    on it. Patch the constant directly instead (matches the established
    pattern in test_skills_writer.py's CLI tests)."""
    skills_dir = tmp_path / "skills"
    with patch("neuralcleave.skills.writer._DEFAULT_SKILLS_DIR", skills_dir):
        yield skills_dir


class TestReviewPending:
    def test_empty_reports_none_pending(self, runner: CliRunner, fresh_queue) -> None:
        result = runner.invoke(cli, ["skills", "review", "pending"])
        assert result.exit_code == 0
        assert "No skill proposals pending" in result.output

    def test_lists_pending_proposal(self, runner: CliRunner, fresh_queue) -> None:
        fresh_queue.propose("greet", SIMPLE_CODE, "Greets someone")
        result = runner.invoke(cli, ["skills", "review", "pending"])
        assert result.exit_code == 0
        assert "greet" in result.output


class TestReviewShow:
    def test_shows_proposal_code(self, runner: CliRunner, fresh_queue) -> None:
        proposal = fresh_queue.propose("greet", SIMPLE_CODE)
        result = runner.invoke(cli, ["skills", "review", "show", proposal.id[:8]])
        assert result.exit_code == 0
        assert "def greet" in result.output

    def test_unknown_id_errors(self, runner: CliRunner, fresh_queue) -> None:
        result = runner.invoke(cli, ["skills", "review", "show", "nonexistent"])
        assert result.exit_code != 0


class TestReviewApprove:
    def test_approve_writes_and_loads_the_skill(
        self, runner: CliRunner, fresh_queue, home_skills_dir: Path
    ) -> None:
        proposal = fresh_queue.propose("greet", SIMPLE_CODE)
        result = runner.invoke(cli, ["skills", "review", "approve", proposal.id[:8]])
        assert result.exit_code == 0
        assert (home_skills_dir / "greet" / "skill.py").exists()

    def test_approve_unknown_id_errors(self, runner: CliRunner, fresh_queue, home_skills_dir: Path) -> None:
        result = runner.invoke(cli, ["skills", "review", "approve", "nonexistent"])
        assert result.exit_code != 0


class TestReviewReject:
    def test_reject_never_writes_to_disk(
        self, runner: CliRunner, fresh_queue, home_skills_dir: Path
    ) -> None:
        proposal = fresh_queue.propose("greet", SIMPLE_CODE)
        result = runner.invoke(cli, ["skills", "review", "reject", proposal.id[:8]])
        assert result.exit_code == 0
        assert not (home_skills_dir / "greet" / "skill.py").exists()

    def test_reject_unknown_id_errors(self, runner: CliRunner, fresh_queue) -> None:
        result = runner.invoke(cli, ["skills", "review", "reject", "nonexistent"])
        assert result.exit_code != 0


class TestSkillsQuarantine:
    def test_quarantine_loaded_skill(self, runner: CliRunner, home_skills_dir: Path) -> None:
        writer = SkillWriter(skills_dir=home_skills_dir)
        writer.write_skill("greet", SIMPLE_CODE)

        result = runner.invoke(cli, ["skills", "quarantine", "greet"])

        assert result.exit_code == 0
        assert "quarantined" in result.output.lower()

    def test_quarantine_not_loaded_skill_errors(self, runner: CliRunner, home_skills_dir: Path) -> None:
        result = runner.invoke(cli, ["skills", "quarantine", "never-written"])
        assert result.exit_code != 0
