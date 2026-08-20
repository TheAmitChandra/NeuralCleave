"""Tests for SkillWriter's propose/apply/reject/quarantine review lifecycle
(P8, 2026-08-17 gap analysis).

write_skill() itself (the immediate, trusted path) is covered by the
existing test_skills_writer.py — these tests cover only the new
review-gated methods that WriteSkillTool now uses instead.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from neuralcleave.skills.review import SkillReviewQueue
from neuralcleave.skills.writer import SkillWriter

SIMPLE_CODE = """\
def greet(name: str) -> str:
    \"\"\"Say hello.\"\"\"
    return f"Hello, {name}!"
"""

BLOCKED_CODE = "import subprocess\nsubprocess.run(['ls'])"


def _make_writer(tmp_path: Path) -> SkillWriter:
    return SkillWriter(skills_dir=tmp_path / "skills")


@pytest.fixture()
def fresh_queue():
    queue = SkillReviewQueue(db_path=None)
    with patch("neuralcleave.skills.review.REVIEW_QUEUE", queue):
        yield queue


class TestProposeSkill:
    def test_propose_returns_pending_proposal(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE, "Greets someone")
        assert proposal.status == "pending"
        assert proposal.name == "greet"

    def test_propose_does_not_write_to_disk(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.propose_skill("greet", SIMPLE_CODE)
        assert not (tmp_path / "skills" / "greet" / "skill.py").exists()

    def test_propose_does_not_load_the_skill(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.propose_skill("greet", SIMPLE_CODE)
        assert "greet" not in writer._loaded_skills

    def test_propose_invalid_name_raises(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        with pytest.raises(ValueError):
            writer.propose_skill("bad name!", SIMPLE_CODE)

    def test_propose_blocked_import_raises(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        with pytest.raises(ValueError, match="subprocess"):
            writer.propose_skill("bad", BLOCKED_CODE)

    def test_propose_persists_in_the_review_queue(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        assert fresh_queue.get(proposal.id) is proposal


class TestApplyProposal:
    def test_apply_writes_to_disk(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.apply_proposal(proposal.id)
        assert (tmp_path / "skills" / "greet" / "skill.py").exists()

    def test_apply_loads_the_skill(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.apply_proposal(proposal.id)
        assert "greet" in writer._loaded_skills

    def test_apply_returns_success_message_with_skill_name(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        message = writer.apply_proposal(proposal.id)
        assert "greet" in message

    def test_apply_marks_proposal_applied(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.apply_proposal(proposal.id)
        assert fresh_queue.get(proposal.id).status == "applied"

    def test_apply_unknown_id_raises(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        with pytest.raises(ValueError):
            writer.apply_proposal("nonexistent")

    def test_apply_already_decided_proposal_raises(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.apply_proposal(proposal.id)
        with pytest.raises(ValueError):
            writer.apply_proposal(proposal.id)


class TestRejectProposal:
    def test_reject_returns_true_for_pending(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        assert writer.reject_proposal(proposal.id) is True

    def test_reject_never_writes_to_disk(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.reject_proposal(proposal.id)
        assert not (tmp_path / "skills" / "greet" / "skill.py").exists()

    def test_reject_marks_proposal_rejected(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.reject_proposal(proposal.id)
        assert fresh_queue.get(proposal.id).status == "rejected"

    def test_reject_unknown_id_returns_false(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        assert writer.reject_proposal("nonexistent") is False

    def test_reject_already_decided_returns_false(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        proposal = writer.propose_skill("greet", SIMPLE_CODE)
        writer.reject_proposal(proposal.id)
        assert writer.reject_proposal(proposal.id) is False


class TestQuarantineSkill:
    def test_quarantine_unloads_the_skill(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.write_skill("greet", SIMPLE_CODE)
        writer.quarantine_skill("greet")
        assert "greet" not in writer._loaded_skills

    def test_quarantine_keeps_the_file_on_disk(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.write_skill("greet", SIMPLE_CODE)
        writer.quarantine_skill("greet")
        assert (tmp_path / "skills" / "greet" / "skill.py").exists()

    def test_quarantine_returns_true_when_loaded(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.write_skill("greet", SIMPLE_CODE)
        assert writer.quarantine_skill("greet") is True

    def test_quarantine_returns_false_when_not_loaded(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        assert writer.quarantine_skill("never-written") is False

    def test_list_skills_reports_quarantined(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.write_skill("greet", SIMPLE_CODE)
        writer.quarantine_skill("greet")
        infos = writer.list_skills()
        assert infos[0].quarantined is True
        assert infos[0].loaded is False

    def test_rewriting_a_quarantined_skill_clears_quarantine(self, tmp_path, fresh_queue):
        writer = _make_writer(tmp_path)
        writer.write_skill("greet", SIMPLE_CODE)
        writer.quarantine_skill("greet")
        writer.write_skill("greet", SIMPLE_CODE)
        infos = writer.list_skills()
        assert infos[0].quarantined is False
        assert infos[0].loaded is True
