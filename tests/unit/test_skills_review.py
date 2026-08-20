"""Tests for neuralcleave.skills.review — SkillReviewQueue persistence and
propose/apply/reject lifecycle (P8, 2026-08-17 gap analysis).
"""

from __future__ import annotations

from neuralcleave.skills.review import VALID_STATUSES, SkillProposal, SkillReviewQueue


class TestPropose:
    def test_propose_creates_pending_proposal(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "def greet(): return 'hi'", "Greets the user")
        assert proposal.status == "pending"
        assert proposal.name == "greet"
        assert proposal.decided_at is None

    def test_propose_assigns_unique_ids(self):
        q = SkillReviewQueue(db_path=None)
        p1 = q.propose("a", "code")
        p2 = q.propose("b", "code")
        assert p1.id != p2.id

    def test_get_returns_the_proposal(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "code")
        assert q.get(proposal.id) is proposal

    def test_get_unknown_id_returns_none(self):
        q = SkillReviewQueue(db_path=None)
        assert q.get("nonexistent") is None


class TestListing:
    def test_list_pending_only_includes_pending(self):
        q = SkillReviewQueue(db_path=None)
        p1 = q.propose("a", "code")
        q.propose("b", "code")
        q.mark_applied(p1.id)
        pending = q.list_pending()
        assert len(pending) == 1
        assert pending[0].name == "b"

    def test_list_all_includes_every_status(self):
        q = SkillReviewQueue(db_path=None)
        p1 = q.propose("a", "code")
        q.propose("b", "code")
        q.mark_rejected(p1.id)
        assert len(q.list_all()) == 2


class TestApplyReject:
    def test_mark_applied_transitions_status(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "code")
        result = q.mark_applied(proposal.id)
        assert result.status == "applied"
        assert result.decided_at is not None

    def test_mark_rejected_transitions_status(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "code")
        result = q.mark_rejected(proposal.id)
        assert result.status == "rejected"

    def test_cannot_apply_an_already_decided_proposal(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "code")
        q.mark_applied(proposal.id)
        result = q.mark_applied(proposal.id)
        assert result is None

    def test_cannot_reject_an_already_decided_proposal(self):
        q = SkillReviewQueue(db_path=None)
        proposal = q.propose("greet", "code")
        q.mark_rejected(proposal.id)
        result = q.mark_applied(proposal.id)
        assert result is None

    def test_unknown_id_returns_none(self):
        q = SkillReviewQueue(db_path=None)
        assert q.mark_applied("nonexistent") is None
        assert q.mark_rejected("nonexistent") is None


class TestPersistence:
    def test_entries_survive_reopening_same_db(self, tmp_path):
        db_path = str(tmp_path / "review.db")
        q1 = SkillReviewQueue(db_path=db_path)
        proposal = q1.propose("greet", "def greet(): pass", "desc")
        q1.close()

        q2 = SkillReviewQueue(db_path=db_path)
        reopened = q2.get(proposal.id)
        assert reopened is not None
        assert reopened.name == "greet"
        assert reopened.code == "def greet(): pass"

    def test_status_transitions_persist_across_reopen(self, tmp_path):
        db_path = str(tmp_path / "review.db")
        q1 = SkillReviewQueue(db_path=db_path)
        proposal = q1.propose("greet", "code")
        q1.mark_applied(proposal.id)
        q1.close()

        q2 = SkillReviewQueue(db_path=db_path)
        assert q2.get(proposal.id).status == "applied"

    def test_no_db_path_keeps_entries_in_memory_only(self):
        q1 = SkillReviewQueue(db_path=None)
        q1.propose("greet", "code")

        q2 = SkillReviewQueue(db_path=None)
        assert q2.list_all() == []


class TestConnectionLifecycle:
    def test_close_clears_connection(self, tmp_path):
        q = SkillReviewQueue(db_path=str(tmp_path / "review.db"))
        assert q._db is not None
        q.close()
        assert q._db is None


class TestModuleSingleton:
    def test_review_queue_singleton_has_persistence_enabled(self):
        from neuralcleave.skills.review import REVIEW_QUEUE

        assert REVIEW_QUEUE._db is not None


class TestSkillProposalToDict:
    def test_to_dict_has_expected_keys(self):
        proposal = SkillProposal(
            id="abc", name="greet", code="code", description="desc",
            status="pending", created_at=1.0, decided_at=None,
        )
        assert set(proposal.to_dict()) == {
            "id", "name", "code", "description", "status", "created_at", "decided_at",
        }


def test_valid_statuses_constant():
    assert VALID_STATUSES == ("pending", "applied", "rejected")
