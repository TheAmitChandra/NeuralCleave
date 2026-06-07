"""Unit tests for the governance module.

Covers:
    - ApprovalWorkflow — state machine, TTL, cancel, mark_executed, expire_stale
    - PolicyEngine     — built-in rules, custom rules, short-circuit order
    - RBACPolicy       — role permissions, actor overrides, require/require_all/require_role
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.core.governance.approvals import (
    ApprovalDecision,
    ApprovalPriority,
    ApprovalRequest,
    ApprovalStatus,
    ApprovalStore,
    ApprovalWorkflow,
)
from app.core.governance.policy import (
    DenyBlockedTierRule,
    PolicyAction,
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    RateLimitRule,
    RequireApprovalForHighRiskRule,
    RequiredPermissionRule,
    TenantToolAllowlistRule,
    TimeWindowRule,
)
from app.core.governance.rbac import (
    Actor,
    Permission,
    RBACPolicy,
    Role,
)

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def store() -> ApprovalStore:
    return ApprovalStore()


@pytest.fixture
def workflow(store: ApprovalStore) -> ApprovalWorkflow:
    return ApprovalWorkflow(store=store, default_ttl_seconds=3600)


@pytest.fixture
def policy() -> PolicyEngine:
    return PolicyEngine(use_defaults=True)


@pytest.fixture
def rbac() -> RBACPolicy:
    return RBACPolicy()


def make_actor(
    role: Role, extra_grants: list[str] | None = None, denials: list[str] | None = None
) -> Actor:
    return Actor(
        actor_id=f"test-{role.value}",
        role=role,
        tenant_id="test-tenant",
        extra_grants=frozenset(extra_grants or []),
        denials=frozenset(denials or []),
    )


# ===========================================================================
# TestApprovalStore
# ===========================================================================


class TestApprovalStore:
    @pytest.mark.asyncio
    async def test_save_and_get(self, store: ApprovalStore) -> None:
        req = ApprovalRequest(
            request_id="req-001",
            actor_id="agent-1",
            tool_name="shell.execute",
            tool_params={},
            action_description="Run command",
            risk_score=90,
            priority=ApprovalPriority.CRITICAL,
            status=ApprovalStatus.PENDING,
            tenant_id="t1",
            created_at=datetime.now(tz=timezone.utc),
            expires_at=datetime.now(tz=timezone.utc) + timedelta(hours=1),
        )
        await store.save(req)
        fetched = await store.get("req-001")
        assert fetched is not None
        assert fetched.actor_id == "agent-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, store: ApprovalStore) -> None:
        assert await store.get("does-not-exist") is None

    @pytest.mark.asyncio
    async def test_list_pending_filters_by_status(self, store: ApprovalStore) -> None:
        now = datetime.now(tz=timezone.utc)
        for i, status in enumerate(
            [ApprovalStatus.PENDING, ApprovalStatus.APPROVED, ApprovalStatus.REJECTED]
        ):
            req = ApprovalRequest(
                request_id=f"req-{i}",
                actor_id="agent",
                tool_name="tool",
                tool_params={},
                action_description="x",
                risk_score=50,
                priority=ApprovalPriority.HIGH,
                status=status,
                tenant_id="t1",
                created_at=now,
                expires_at=now + timedelta(hours=1),
            )
            await store.save(req)
        pending = await store.list_pending()
        assert len(pending) == 1
        assert pending[0].request_id == "req-0"

    @pytest.mark.asyncio
    async def test_delete(self, store: ApprovalStore) -> None:
        now = datetime.now(tz=timezone.utc)
        req = ApprovalRequest(
            request_id="req-del",
            actor_id="agent",
            tool_name="tool",
            tool_params={},
            action_description="x",
            risk_score=50,
            priority=ApprovalPriority.MEDIUM,
            status=ApprovalStatus.PENDING,
            tenant_id="t1",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )
        await store.save(req)
        await store.delete("req-del")
        assert await store.get("req-del") is None


# ===========================================================================
# TestApprovalWorkflow — request_approval
# ===========================================================================


class TestApprovalWorkflowRequest:
    @pytest.mark.asyncio
    async def test_creates_pending_request(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="agent-1",
            action_description="Delete backup",
            risk_score=92,
            tool_name="shell.execute",
            tool_params={"command": "rm -rf /backups"},
            tenant_id="t1",
        )
        assert req.status == ApprovalStatus.PENDING
        assert req.priority == ApprovalPriority.CRITICAL
        assert req.request_id != ""
        assert req.request_hash != ""

    @pytest.mark.asyncio
    async def test_priority_derived_from_risk_score(self, workflow: ApprovalWorkflow) -> None:
        r_crit = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=90,
            tool_name="t",
            tool_params={},
        )
        r_high = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=70,
            tool_name="t",
            tool_params={},
        )
        r_med = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=40,
            tool_name="t",
            tool_params={},
        )
        r_low = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=10,
            tool_name="t",
            tool_params={},
        )
        assert r_crit.priority == ApprovalPriority.CRITICAL
        assert r_high.priority == ApprovalPriority.HIGH
        assert r_med.priority == ApprovalPriority.MEDIUM
        assert r_low.priority == ApprovalPriority.LOW

    @pytest.mark.asyncio
    async def test_persisted_in_store(
        self, workflow: ApprovalWorkflow, store: ApprovalStore
    ) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        fetched = await store.get(req.request_id)
        assert fetched is not None

    @pytest.mark.asyncio
    async def test_to_dict_contains_required_keys(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        d = req.to_dict()
        for key in (
            "request_id",
            "actor_id",
            "tool_name",
            "status",
            "risk_score",
            "priority",
            "created_at",
            "expires_at",
            "request_hash",
        ):
            assert key in d


# ===========================================================================
# TestApprovalWorkflow — approve / reject / cancel
# ===========================================================================


class TestApprovalWorkflowDecisions:
    @pytest.mark.asyncio
    async def test_approve_transitions_to_approved(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        decision = await workflow.approve(req.request_id, operator_id="ops-1")
        assert decision.new_status == ApprovalStatus.APPROVED
        fetched = await workflow.get(req.request_id)
        assert fetched.status == ApprovalStatus.APPROVED
        assert fetched.decided_by == "ops-1"

    @pytest.mark.asyncio
    async def test_reject_transitions_to_rejected(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        decision = await workflow.reject(req.request_id, operator_id="ops-2", reason="too risky")
        assert decision.new_status == ApprovalStatus.REJECTED
        fetched = await workflow.get(req.request_id)
        assert fetched.rejection_reason == "too risky"

    @pytest.mark.asyncio
    async def test_cannot_approve_already_decided(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        await workflow.approve(req.request_id, operator_id="ops-1")
        with pytest.raises(ValueError, match="not PENDING"):
            await workflow.approve(req.request_id, operator_id="ops-1")

    @pytest.mark.asyncio
    async def test_cancel_by_actor(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="agent-007",
            action_description="x",
            risk_score=50,
            tool_name="t",
            tool_params={},
        )
        decision = await workflow.cancel(req.request_id, actor_id="agent-007")
        assert decision.new_status == ApprovalStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_by_wrong_actor_raises(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="agent-007",
            action_description="x",
            risk_score=50,
            tool_name="t",
            tool_params={},
        )
        with pytest.raises(PermissionError):
            await workflow.cancel(req.request_id, actor_id="agent-999")

    @pytest.mark.asyncio
    async def test_mark_executed(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        await workflow.approve(req.request_id, operator_id="ops-1")
        decision = await workflow.mark_executed(req.request_id, operator_id="ops-1")
        assert decision.new_status == ApprovalStatus.EXECUTED

    @pytest.mark.asyncio
    async def test_mark_executed_without_approval_raises(self, workflow: ApprovalWorkflow) -> None:
        req = await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
        )
        with pytest.raises(ValueError):
            await workflow.mark_executed(req.request_id, operator_id="ops-1")

    @pytest.mark.asyncio
    async def test_get_nonexistent_returns_none(self, workflow: ApprovalWorkflow) -> None:
        assert await workflow.get("bad-id") is None

    @pytest.mark.asyncio
    async def test_list_pending(self, workflow: ApprovalWorkflow) -> None:
        await workflow.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
            tenant_id="t1",
        )
        await workflow.request_approval(
            actor_id="b",
            action_description="y",
            risk_score=70,
            tool_name="t",
            tool_params={},
            tenant_id="t2",
        )
        all_pending = await workflow.list_pending()
        t1_pending = await workflow.list_pending(tenant_id="t1")
        assert len(all_pending) == 2
        assert len(t1_pending) == 1

    @pytest.mark.asyncio
    async def test_expire_stale(self) -> None:
        store = ApprovalStore()
        wf = ApprovalWorkflow(store=store, default_ttl_seconds=1)
        req = await wf.request_approval(
            actor_id="a",
            action_description="x",
            risk_score=80,
            tool_name="t",
            tool_params={},
            ttl_seconds=1,
        )
        # Force expire by backdating the request
        req.expires_at = datetime.now(tz=timezone.utc) - timedelta(seconds=1)
        await store.save(req)
        expired = await wf.expire_stale()
        assert req.request_id in expired
        fetched = await wf.get(req.request_id)
        assert fetched.status == ApprovalStatus.EXPIRED


# ===========================================================================
# TestPolicyRules
# ===========================================================================


class TestDenyBlockedTierRule:
    def test_triggers_above_threshold(self) -> None:
        rule = DenyBlockedTierRule(deny_threshold=86)
        ctx = PolicyContext(tool_name="shell.execute", risk_score=90, actor_id="a")
        d = rule.evaluate(ctx)
        assert d is not None
        assert d.action == PolicyAction.APPROVE

    def test_no_match_below_threshold(self) -> None:
        rule = DenyBlockedTierRule(deny_threshold=86)
        ctx = PolicyContext(tool_name="shell.execute", risk_score=85, actor_id="a")
        assert rule.evaluate(ctx) is None


class TestRequireApprovalForHighRiskRule:
    def test_triggers_in_range(self) -> None:
        rule = RequireApprovalForHighRiskRule(low=61, high=85)
        ctx = PolicyContext(tool_name="browser.navigate", risk_score=75, actor_id="a")
        d = rule.evaluate(ctx)
        assert d is not None
        assert d.action == PolicyAction.APPROVE

    def test_no_match_below_range(self) -> None:
        rule = RequireApprovalForHighRiskRule(low=61, high=85)
        ctx = PolicyContext(tool_name="browser.navigate", risk_score=40, actor_id="a")
        assert rule.evaluate(ctx) is None

    def test_no_match_above_range(self) -> None:
        rule = RequireApprovalForHighRiskRule(low=61, high=85)
        ctx = PolicyContext(tool_name="browser.navigate", risk_score=90, actor_id="a")
        assert rule.evaluate(ctx) is None


class TestTenantToolAllowlistRule:
    def test_denies_unlisted_tool(self) -> None:
        rule = TenantToolAllowlistRule(allowlists={"t1": {"db.query", "file.read"}})
        ctx = PolicyContext(tool_name="shell.execute", risk_score=30, actor_id="a", tenant_id="t1")
        d = rule.evaluate(ctx)
        assert d is not None
        assert d.action == PolicyAction.DENY

    def test_allows_listed_tool(self) -> None:
        rule = TenantToolAllowlistRule(allowlists={"t1": {"db.query", "file.read"}})
        ctx = PolicyContext(tool_name="db.query", risk_score=20, actor_id="a", tenant_id="t1")
        assert rule.evaluate(ctx) is None

    def test_no_restriction_when_no_allowlist(self) -> None:
        rule = TenantToolAllowlistRule()
        ctx = PolicyContext(tool_name="anything", risk_score=50, actor_id="a", tenant_id="t1")
        assert rule.evaluate(ctx) is None


class TestRateLimitRule:
    def test_allows_under_limit(self) -> None:
        rule = RateLimitRule(max_calls=5, window_seconds=60)
        ctx = PolicyContext(tool_name="t", risk_score=10, actor_id="a", tenant_id="x")
        for _ in range(4):
            assert rule.evaluate(ctx) is None

    def test_denies_over_limit(self) -> None:
        rule = RateLimitRule(max_calls=3, window_seconds=60)
        ctx = PolicyContext(tool_name="t", risk_score=10, actor_id="a", tenant_id="x")
        for _ in range(3):
            rule.evaluate(ctx)
        d = rule.evaluate(ctx)
        assert d is not None
        assert d.action == PolicyAction.DENY


class TestRequiredPermissionRule:
    def test_denies_missing_permission(self) -> None:
        rule = RequiredPermissionRule(tool_permission_map={"shell.execute": ["shell_access"]})
        ctx = PolicyContext(
            tool_name="shell.execute",
            risk_score=30,
            actor_id="a",
            actor_permissions=["file_read"],
        )
        d = rule.evaluate(ctx)
        assert d is not None
        assert d.action == PolicyAction.DENY

    def test_allows_with_permission(self) -> None:
        rule = RequiredPermissionRule(tool_permission_map={"shell.execute": ["shell_access"]})
        ctx = PolicyContext(
            tool_name="shell.execute",
            risk_score=30,
            actor_id="a",
            actor_permissions=["shell_access"],
        )
        assert rule.evaluate(ctx) is None

    def test_no_restriction_for_unknown_tool(self) -> None:
        rule = RequiredPermissionRule()
        ctx = PolicyContext(tool_name="unknown", risk_score=10, actor_id="a")
        assert rule.evaluate(ctx) is None


# ===========================================================================
# TestPolicyEngine
# ===========================================================================


class TestPolicyEngine:
    def test_default_allow_for_low_risk(self, policy: PolicyEngine) -> None:
        d = policy.evaluate(tool_name="db.query", risk_score=20, actor_id="a")
        assert d.action == PolicyAction.ALLOW

    def test_approve_for_high_risk(self, policy: PolicyEngine) -> None:
        d = policy.evaluate(tool_name="shell.execute", risk_score=75, actor_id="a")
        assert d.action == PolicyAction.APPROVE

    def test_approve_for_critical_risk(self, policy: PolicyEngine) -> None:
        d = policy.evaluate(tool_name="shell.execute", risk_score=92, actor_id="a")
        assert d.action == PolicyAction.APPROVE

    def test_first_matching_rule_wins(self) -> None:
        engine = PolicyEngine(use_defaults=False)
        engine.add_rule(DenyBlockedTierRule(deny_threshold=50))
        engine.add_rule(RequireApprovalForHighRiskRule(low=50, high=90))
        # DenyBlockedTierRule fires first at score=60 → should be APPROVE
        d = engine.evaluate(tool_name="t", risk_score=60, actor_id="a")
        assert d.rule_name == "deny_blocked_tier"

    def test_add_rule_appends(self, policy: PolicyEngine) -> None:
        before = len(policy.rule_names)
        policy.add_rule(TenantToolAllowlistRule())
        assert len(policy.rule_names) == before + 1

    def test_remove_rule(self, policy: PolicyEngine) -> None:
        policy.add_rule(TenantToolAllowlistRule())
        removed = policy.remove_rule("tenant_tool_allowlist")
        assert removed is True
        assert "tenant_tool_allowlist" not in policy.rule_names

    def test_remove_nonexistent_rule(self, policy: PolicyEngine) -> None:
        assert policy.remove_rule("does_not_exist") is False

    def test_decision_is_denied(self) -> None:
        engine = PolicyEngine(use_defaults=False)
        engine.add_rule(TenantToolAllowlistRule(allowlists={"t1": {"only.tool"}}))
        d = engine.evaluate(tool_name="other.tool", risk_score=10, actor_id="a", tenant_id="t1")
        assert d.is_denied

    def test_decision_needs_approval(self, policy: PolicyEngine) -> None:
        d = policy.evaluate(tool_name="t", risk_score=70, actor_id="a")
        assert d.needs_approval

    def test_decision_is_allowed(self, policy: PolicyEngine) -> None:
        d = policy.evaluate(tool_name="db.query", risk_score=15, actor_id="a")
        assert d.is_allowed


# ===========================================================================
# TestRBACPolicy — role permissions
# ===========================================================================


class TestRBACPolicyRolePermissions:
    def test_admin_has_all_permissions(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.ADMIN)
        assert rbac.has_permission(actor, Permission.USER_DELETE.value)
        assert rbac.has_permission(actor, Permission.POLICY_WRITE.value)
        assert rbac.has_permission(actor, Permission.AUDIT_EXPORT.value)

    def test_developer_lacks_user_delete(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.DEVELOPER)
        assert not rbac.has_permission(actor, Permission.USER_DELETE.value)

    def test_developer_can_execute_agent(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.DEVELOPER)
        assert rbac.has_permission(actor, Permission.AGENT_EXECUTE.value)

    def test_operator_can_decide_approvals(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.OPERATOR)
        assert rbac.has_permission(actor, Permission.APPROVAL_DECIDE.value)

    def test_viewer_cannot_execute(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER)
        assert not rbac.has_permission(actor, Permission.AGENT_EXECUTE.value)
        assert not rbac.has_permission(actor, Permission.TOOL_EXECUTE.value)

    def test_auditor_can_only_read_audit(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.AUDITOR)
        assert rbac.has_permission(actor, Permission.AUDIT_READ.value)
        assert rbac.has_permission(actor, Permission.AUDIT_EXPORT.value)
        assert not rbac.has_permission(actor, Permission.AGENT_READ.value)

    def test_role_permissions_static(self, rbac: RBACPolicy) -> None:
        perms = rbac.role_permissions(Role.VIEWER)
        assert Permission.AGENT_READ.value in perms
        assert Permission.USER_DELETE.value not in perms


# ===========================================================================
# TestRBACPolicy — actor overrides
# ===========================================================================


class TestRBACPolicyActorOverrides:
    def test_extra_grant_extends_permissions(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER, extra_grants=[Permission.TOOL_EXECUTE.value])
        assert rbac.has_permission(actor, Permission.TOOL_EXECUTE.value)

    def test_denial_revokes_role_permission(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.DEVELOPER, denials=[Permission.AGENT_DELETE.value])
        assert not rbac.has_permission(actor, Permission.AGENT_DELETE.value)

    def test_denial_overrides_extra_grant(self, rbac: RBACPolicy) -> None:
        actor = make_actor(
            Role.VIEWER,
            extra_grants=[Permission.TOOL_EXECUTE.value],
            denials=[Permission.TOOL_EXECUTE.value],
        )
        assert not rbac.has_permission(actor, Permission.TOOL_EXECUTE.value)


# ===========================================================================
# TestRBACPolicy — require / require_all / require_role
# ===========================================================================


class TestRBACPolicyRequire:
    def test_require_passes_when_allowed(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.ADMIN)
        rbac.require(actor, Permission.USER_DELETE.value)  # should not raise

    def test_require_raises_when_denied(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER)
        with pytest.raises(PermissionError, match="lacks permission"):
            rbac.require(actor, Permission.USER_DELETE.value)

    def test_require_all_passes(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.DEVELOPER)
        rbac.require_all(actor, [Permission.AGENT_CREATE.value, Permission.WORKFLOW_RUN.value])

    def test_require_all_raises_on_partial(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER)
        with pytest.raises(PermissionError, match="lacks permissions"):
            rbac.require_all(actor, [Permission.AGENT_READ.value, Permission.USER_DELETE.value])

    def test_has_any_true(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER)
        assert rbac.has_any(actor, [Permission.AGENT_READ.value, Permission.USER_DELETE.value])

    def test_has_any_false(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.AUDITOR)
        assert not rbac.has_any(actor, [Permission.AGENT_READ.value, Permission.TOOL_EXECUTE.value])

    def test_require_role_passes(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.OPERATOR)
        rbac.require_role(actor, Role.OPERATOR, Role.ADMIN)  # should not raise

    def test_require_role_raises(self, rbac: RBACPolicy) -> None:
        actor = make_actor(Role.VIEWER)
        with pytest.raises(PermissionError, match="not in allowed roles"):
            rbac.require_role(actor, Role.ADMIN, Role.OPERATOR)
