"""Tests for neuralcleave.tools.approval_policy — persistent exec-approval
allowlist + security/ask mode decisions (P5, 2026-08-17 gap analysis).
"""

from __future__ import annotations

import pytest

from neuralcleave.tools.approval_policy import (
    VALID_ASK_MODES,
    VALID_SECURITY_MODES,
    AllowlistEntry,
    ApprovalPolicy,
)


class TestConstruction:
    def test_rejects_invalid_security_mode(self):
        with pytest.raises(ValueError, match="security mode"):
            ApprovalPolicy(db_path=None, security="nope")

    def test_rejects_invalid_ask_mode(self):
        with pytest.raises(ValueError, match="ask mode"):
            ApprovalPolicy(db_path=None, ask="nope")

    def test_valid_modes_constants(self):
        assert VALID_SECURITY_MODES == ("deny", "allowlist", "full")
        assert VALID_ASK_MODES == ("off", "on-miss", "always")


class TestAllowlistEntryMatching:
    def test_exact_pattern_matches(self):
        entry = AllowlistEntry(id=1, pattern="git", arg_pattern=None, created_at=0.0)
        assert entry.matches("git", "git log") is True

    def test_glob_pattern_matches(self):
        entry = AllowlistEntry(id=1, pattern="git*", arg_pattern=None, created_at=0.0)
        assert entry.matches("git-lfs", "git-lfs pull") is True

    def test_non_matching_pattern(self):
        entry = AllowlistEntry(id=1, pattern="git", arg_pattern=None, created_at=0.0)
        assert entry.matches("curl", "curl https://x") is False

    def test_arg_pattern_must_also_match(self):
        entry = AllowlistEntry(id=1, pattern="git", arg_pattern=r"^git log", created_at=0.0)
        assert entry.matches("git", "git log --oneline") is True
        assert entry.matches("git", "git push --force") is False

    def test_to_dict_has_expected_keys(self):
        entry = AllowlistEntry(id=1, pattern="git", arg_pattern=None, created_at=123.0)
        d = entry.to_dict()
        assert d == {"id": 1, "pattern": "git", "arg_pattern": None, "created_at": 123.0}


class TestAllowlistPersistence:
    def test_add_and_list_entry(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"))
        policy.add_entry("git")
        entries = policy.list_entries()
        assert len(entries) == 1
        assert entries[0].pattern == "git"

    def test_remove_entry(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"))
        entry = policy.add_entry("git")
        removed = policy.remove_entry(entry.id)
        assert removed is True
        assert policy.list_entries() == []

    def test_remove_nonexistent_entry_returns_false(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"))
        assert policy.remove_entry(999) is False

    def test_entries_survive_reopening_same_db(self, tmp_path):
        db_path = str(tmp_path / "p.db")
        policy1 = ApprovalPolicy(db_path=db_path)
        policy1.add_entry("git")
        policy1.close()

        policy2 = ApprovalPolicy(db_path=db_path)
        assert len(policy2.list_entries()) == 1

    def test_no_db_path_disables_persistence(self):
        policy = ApprovalPolicy(db_path=None)
        entry = policy.add_entry("git")
        assert entry.id == -1
        assert policy.list_entries() == []

    def test_matches_checks_all_entries(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"))
        policy.add_entry("git")
        policy.add_entry("curl")
        assert policy.matches("curl", "curl -s x") is True
        assert policy.matches("rm", "rm -rf /") is False


class TestSecurityModeFull:
    def test_full_always_auto_approves(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="full")
        assert policy.should_auto_approve("rm") is True

    def test_full_never_prompts(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="full")
        assert policy.should_prompt("rm") is False


class TestSecurityModeDeny:
    def test_deny_never_auto_approves(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="deny")
        policy.add_entry("git")
        assert policy.should_auto_approve("git") is False

    def test_deny_never_prompts(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="deny")
        assert policy.should_prompt("git") is False


class TestSecurityModeAllowlist:
    def test_matched_entry_auto_approved_by_default(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="allowlist", ask="on-miss")
        policy.add_entry("git")
        assert policy.should_auto_approve("git") is True
        assert policy.should_prompt("git") is False

    def test_unmatched_falls_through_to_prompt_on_miss(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="allowlist", ask="on-miss")
        assert policy.should_auto_approve("curl") is False
        assert policy.should_prompt("curl") is True

    def test_ask_off_denies_unmatched_silently(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="allowlist", ask="off")
        assert policy.should_auto_approve("curl") is False
        assert policy.should_prompt("curl") is False

    def test_ask_off_still_auto_approves_matched(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="allowlist", ask="off")
        policy.add_entry("git")
        assert policy.should_auto_approve("git") is True

    def test_ask_always_prompts_even_on_match(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"), security="allowlist", ask="always")
        policy.add_entry("git")
        assert policy.should_auto_approve("git") is False
        assert policy.should_prompt("git") is True


class TestConnectionLifecycle:
    def test_close_clears_connection(self, tmp_path):
        policy = ApprovalPolicy(db_path=str(tmp_path / "p.db"))
        assert policy._db is not None
        policy.close()
        assert policy._db is None

    def test_close_on_disabled_persistence_is_noop(self):
        policy = ApprovalPolicy(db_path=None)
        policy.close()  # must not raise
        assert policy._db is None


class TestModuleSingleton:
    def test_policy_singleton_has_persistence_enabled(self):
        """Regression guard: proves POLICY isn't silently in-memory-only.
        The test session routes it to sqlite ':memory:' via tests/conftest.py."""
        from neuralcleave.tools.approval_policy import POLICY

        assert POLICY._db is not None

    def test_policy_singleton_default_modes(self):
        from neuralcleave.tools.approval_policy import POLICY

        assert POLICY.security == "allowlist"
        assert POLICY.ask == "on-miss"
