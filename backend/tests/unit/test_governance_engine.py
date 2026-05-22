"""Tests for GovernanceEngine — unified RBAC + policy + approval facade."""

from __future__ import annotations

import pytest

from app.core.governance.approvals import ApprovalStatus, ApprovalStore, ApprovalWorkflow
from app.core.governance.governance_engine import GovernanceEngine, GovernanceResult
from app.core.governance.policy import PolicyEngine
from app.core.governance.rbac import Actor, Permission, RBACPolicy, Role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_actor(role: Role, tenant_id: str = "t1") -> Actor:
    return Actor(actor_id=f"test-{role.value}", role=role, tenant_id=tenant_id)


@pytest.fixture
def engine() -> GovernanceEngine:
    store = ApprovalStore()
    workflow = ApprovalWorkflow(store=store, default_ttl_seconds=3600)
    return GovernanceEngine(workflow=workflow, approval_threshold=85)


# ===========================================================================
# TestGovernanceEngineInit
# ===========================================================================

class TestGovernanceEngineInit:
    def test_default_threshold(self) -> None:
        e = GovernanceEngine()
        assert e.approval_threshold == 85

    def test_custom_threshold(self) -> None:
        e = GovernanceEngine(approval_threshold=70)
        assert e.approval_threshold == 70

    def test_threshold_setter_valid(self) -> None:
        e = GovernanceEngine()
        e.approval_threshold = 60
        assert e.approval_threshold == 60

    def test_threshold_setter_invalid_raises(self) -> None:
        e = GovernanceEngine()
        with pytest.raises(ValueError, match="between 0 and 100"):
            e.approval_threshold = 101

    def test_threshold_setter_negative_raises(self) -> None:
        e = GovernanceEngine()
        with pytest.raises(ValueError):
            e.approval_threshold = -1


# ===========================================================================
# TestGovernanceRBACDenial
# ===========================================================================

class TestGovernanceRBACDenial:
    async def test_viewer_cannot_create_agent(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.VIEWER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.AGENT_CREATE.value,
            resource="agent-service",
        )
        assert result.approved is False
        assert result.rbac_allowed is False
        assert "RBAC" in result.denial_reason

    async def test_auditor_cannot_execute_tool(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.AUDITOR)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="shell.execute",
        )
        assert result.approved is False
        assert result.rbac_allowed is False

    async def test_rbac_denied_result_no_approval_request(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.VIEWER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.AGENT_DELETE.value,
            resource="agent-x",
        )
        assert result.approval_request is None
        assert result.requires_human_approval is False


# ===========================================================================
# TestGovernanceApproval
# ===========================================================================

class TestGovernanceApproval:
    async def test_high_risk_triggers_approval(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="shell.execute",
            risk_score=90,
            action_description="Run dangerous command",
        )
        assert result.approved is False
        assert result.requires_human_approval is True
        assert result.approval_request is not None
        assert result.approval_request.status == ApprovalStatus.PENDING

    async def test_approval_request_has_correct_actor(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="tool-x",
            risk_score=90,
        )
        assert result.approval_request.actor_id == actor.actor_id

    async def test_approval_request_has_correct_tenant(
        self, engine: GovernanceEngine
    ) -> None:
        actor = Actor(actor_id="dev-1", role=Role.DEVELOPER, tenant_id="tenant-abc")
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="tool-x",
            risk_score=90,
        )
        assert result.approval_request.tenant_id == "tenant-abc"

    async def test_below_threshold_does_not_require_approval(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="safe-tool",
            risk_score=50,
        )
        assert result.approved is True
        assert result.requires_human_approval is False
        assert result.approval_request is None

    async def test_exactly_at_threshold_requires_approval(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="borderline-tool",
            risk_score=85,
        )
        assert result.requires_human_approval is True

    async def test_just_below_threshold_approved(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="safe-tool",
            risk_score=60,  # below policy rule range [61, 85] and engine threshold 85
        )
        assert result.approved is True


# ===========================================================================
# TestGovernanceApproveReject
# ===========================================================================

class TestGovernanceApproveReject:
    async def test_approve_action_transitions_to_approved(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="tool-y",
            risk_score=90,
        )
        req_id = result.approval_request.request_id
        await engine.approve_action(req_id, operator_id="ops-1")
        fetched = await engine.get_approval_request(req_id)
        assert fetched.status == ApprovalStatus.APPROVED

    async def test_reject_action_transitions_to_rejected(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="tool-z",
            risk_score=90,
        )
        req_id = result.approval_request.request_id
        await engine.reject_action(req_id, operator_id="ops-2", reason="too risky")
        fetched = await engine.get_approval_request(req_id)
        assert fetched.status == ApprovalStatus.REJECTED
        assert fetched.rejection_reason == "too risky"

    async def test_get_pending_approvals_lists_all(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        for _ in range(3):
            await engine.authorize(
                actor=actor,
                action=Permission.TOOL_EXECUTE.value,
                resource="risky-tool",
                risk_score=90,
            )
        pending = await engine.get_pending_approvals()
        assert len(pending) == 3

    async def test_get_approval_request_nonexistent_returns_none(
        self, engine: GovernanceEngine
    ) -> None:
        result = await engine.get_approval_request("nonexistent-id")
        assert result is None


# ===========================================================================
# TestGovernanceCan
# ===========================================================================

class TestGovernanceCan:
    def test_admin_can_everything(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.ADMIN)
        assert engine.can(actor, Permission.USER_DELETE.value) is True
        assert engine.can(actor, Permission.POLICY_WRITE.value) is True

    def test_viewer_can_read_only(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.VIEWER)
        assert engine.can(actor, Permission.AGENT_READ.value) is True
        assert engine.can(actor, Permission.AGENT_CREATE.value) is False

    def test_auditor_can_audit_only(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.AUDITOR)
        assert engine.can(actor, Permission.AUDIT_READ.value) is True
        assert engine.can(actor, Permission.AGENT_READ.value) is False

    def test_require_raises_on_missing_permission(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.VIEWER)
        with pytest.raises(PermissionError):
            engine.require(actor, Permission.USER_DELETE.value)

    def test_require_passes_with_correct_permission(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.ADMIN)
        engine.require(actor, Permission.USER_DELETE.value)  # should not raise


# ===========================================================================
# TestGovernanceResultToDict
# ===========================================================================

class TestGovernanceResultToDict:
    async def test_approved_result_dict(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="safe-tool",
            risk_score=10,
        )
        d = result.to_dict()
        assert d["approved"] is True
        assert d["rbac_allowed"] is True
        assert d["requires_human_approval"] is False
        assert d["approval_request_id"] is None

    async def test_denied_rbac_result_dict(self, engine: GovernanceEngine) -> None:
        actor = make_actor(Role.VIEWER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.AGENT_CREATE.value,
            resource="agent-svc",
        )
        d = result.to_dict()
        assert d["approved"] is False
        assert d["rbac_allowed"] is False

    async def test_approval_required_result_dict(
        self, engine: GovernanceEngine
    ) -> None:
        actor = make_actor(Role.DEVELOPER)
        result = await engine.authorize(
            actor=actor,
            action=Permission.TOOL_EXECUTE.value,
            resource="risky-tool",
            risk_score=90,
        )
        d = result.to_dict()
        assert d["approved"] is False
        assert d["requires_human_approval"] is True
        assert d["approval_request_id"] is not None
