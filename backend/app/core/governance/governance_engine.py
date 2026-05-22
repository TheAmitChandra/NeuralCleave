"""Governance Engine — unified facade for RBAC, policy, and approval workflows.

This module wires together the three governance subsystems:
    - ``RBACPolicy``        : permission checks for actors
    - ``PolicyEngine``      : rule-based action allow/deny
    - ``ApprovalWorkflow``  : human-in-the-loop approval for high-risk actions

Usage::

    engine = GovernanceEngine()

    actor = Actor(actor_id="agent-1", role=Role.DEVELOPER, tenant_id="t1")
    result = await engine.authorize(
        actor=actor,
        action="tool:execute",
        resource="shell.execute",
        risk_score=50,
    )
    # result.approved is True/False; result.requires_human_approval if score >= threshold

    # High-risk action triggers approval workflow:
    result = await engine.authorize(
        actor=actor,
        action="tool:execute",
        resource="shell.execute",
        risk_score=90,
        action_description="Run rm -rf",
        tool_params={"command": "rm -rf /tmp"},
    )
    # result.approval_request is set; a human operator must approve before execution
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

from app.core.governance.approvals import (
    ApprovalRequest,
    ApprovalStore,
    ApprovalWorkflow,
)
from app.core.governance.policy import PolicyAction, PolicyDecision, PolicyEngine
from app.core.governance.rbac import Actor, Permission, RBACPolicy, Role

logger = structlog.get_logger(__name__)

# Default risk score threshold above which human approval is required
_DEFAULT_APPROVAL_THRESHOLD = 85


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class GovernanceResult:
    """The outcome of a governance authorization check.

    Attributes:
        approved:                True if the action is allowed to proceed.
        requires_human_approval: True if a human approval request was raised.
        approval_request:        Set when ``requires_human_approval`` is True.
        rbac_allowed:            Outcome of the RBAC permission check.
        policy_decision:         Outcome of the policy check (or None if skipped).
        denial_reason:           Human-readable reason when ``approved`` is False.
    """

    approved: bool
    requires_human_approval: bool = False
    approval_request: ApprovalRequest | None = None
    rbac_allowed: bool = True
    policy_decision: PolicyDecision | None = None
    denial_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "approved": self.approved,
            "requires_human_approval": self.requires_human_approval,
            "approval_request_id": (
                self.approval_request.request_id if self.approval_request else None
            ),
            "rbac_allowed": self.rbac_allowed,
            "policy_decision": (
                self.policy_decision.action.value if self.policy_decision else None
            ),
            "denial_reason": self.denial_reason,
        }


# ---------------------------------------------------------------------------
# GovernanceEngine
# ---------------------------------------------------------------------------


class GovernanceEngine:
    """Unified governance decision point.

    Parameters:
        rbac:                 ``RBACPolicy`` instance to use.
        policy:               ``PolicyEngine`` instance to use.
        workflow:             ``ApprovalWorkflow`` instance for human approvals.
        approval_threshold:   Risk score at or above which human approval is needed.
    """

    def __init__(
        self,
        rbac: RBACPolicy | None = None,
        policy: PolicyEngine | None = None,
        workflow: ApprovalWorkflow | None = None,
        approval_threshold: int = _DEFAULT_APPROVAL_THRESHOLD,
    ) -> None:
        self._rbac = rbac or RBACPolicy()
        self._policy = policy or PolicyEngine(use_defaults=True)
        self._store = ApprovalStore()
        self._workflow = workflow or ApprovalWorkflow(store=self._store)
        self._threshold = approval_threshold

    # ------------------------------------------------------------------
    # Main authorization entry point
    # ------------------------------------------------------------------

    async def authorize(
        self,
        *,
        actor: Actor,
        action: str,
        resource: str,
        risk_score: int = 0,
        action_description: str = "",
        tool_params: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
    ) -> GovernanceResult:
        """Run the full governance pipeline for an action request.

        Pipeline:
            1. RBAC check — does the actor have the permission for ``action``?
            2. Policy check — does the engine allow the action/resource pair?
            3. Risk threshold — if ``risk_score >= approval_threshold``, raise
               a human-approval request and return ``requires_human_approval=True``.

        Returns a ``GovernanceResult`` describing the decision.
        """
        # Step 1: RBAC
        rbac_allowed = self._rbac.has_permission(actor, action)
        if not rbac_allowed:
            logger.warning(
                "governance.rbac_denied",
                actor_id=actor.actor_id,
                action=action,
            )
            return GovernanceResult(
                approved=False,
                rbac_allowed=False,
                denial_reason=f"RBAC: actor lacks permission '{action}'",
            )

        # Step 2: Policy
        policy_decision: PolicyDecision | None = None
        try:
            policy_decision = self._policy.evaluate(
                tool_name=resource,
                risk_score=risk_score,
                actor_id=actor.actor_id,
                tenant_id=actor.tenant_id,
                actor_permissions=list(actor.effective_permissions),
                tool_params=tool_params or {},
                extra=context or {},
            )
            if policy_decision.action == PolicyAction.DENY:
                logger.warning(
                    "governance.policy_denied",
                    actor_id=actor.actor_id,
                    action=action,
                    resource=resource,
                    rule=policy_decision.rule_name,
                )
                return GovernanceResult(
                    approved=False,
                    rbac_allowed=True,
                    policy_decision=policy_decision,
                    denial_reason=(
                        f"Policy denied: {policy_decision.rule_name or 'default'}"
                    ),
                )
        except Exception:
            # PolicyEngine may raise when no rule matches — treat as allowed
            policy_decision = None

        # Step 3: Risk threshold OR policy APPROVE → human approval
        needs_approval = risk_score >= self._threshold or (
            policy_decision is not None
            and policy_decision.action == PolicyAction.APPROVE
        )
        if needs_approval:
            approval_request = await self._workflow.request_approval(
                actor_id=actor.actor_id,
                action_description=action_description or f"{action} on {resource}",
                risk_score=risk_score,
                tool_name=resource,
                tool_params=tool_params or {},
                tenant_id=actor.tenant_id,
                context=context or {},
            )
            logger.info(
                "governance.approval_required",
                actor_id=actor.actor_id,
                resource=resource,
                risk_score=risk_score,
                request_id=approval_request.request_id,
            )
            return GovernanceResult(
                approved=False,
                requires_human_approval=True,
                approval_request=approval_request,
                rbac_allowed=True,
                policy_decision=policy_decision,
                denial_reason="Risk score requires human approval",
            )

        # All checks passed
        logger.info(
            "governance.approved",
            actor_id=actor.actor_id,
            action=action,
            resource=resource,
            risk_score=risk_score,
        )
        return GovernanceResult(
            approved=True,
            rbac_allowed=True,
            policy_decision=policy_decision,
        )

    # ------------------------------------------------------------------
    # Approval management helpers
    # ------------------------------------------------------------------

    async def approve_action(
        self, request_id: str, *, operator_id: str
    ) -> None:
        """Approve a pending high-risk action request."""
        await self._workflow.approve(request_id, operator_id=operator_id)

    async def reject_action(
        self, request_id: str, *, operator_id: str, reason: str = ""
    ) -> None:
        """Reject a pending high-risk action request."""
        await self._workflow.reject(
            request_id, operator_id=operator_id, reason=reason
        )

    async def get_pending_approvals(
        self, tenant_id: str | None = None
    ) -> list[ApprovalRequest]:
        """Return all pending approval requests."""
        return await self._workflow.list_pending(tenant_id)

    async def get_approval_request(
        self, request_id: str
    ) -> ApprovalRequest | None:
        """Fetch a specific approval request by ID."""
        return await self._workflow.get(request_id)

    # ------------------------------------------------------------------
    # Direct RBAC helpers
    # ------------------------------------------------------------------

    def can(self, actor: Actor, permission: str) -> bool:
        """Return True if the actor has the given permission."""
        return self._rbac.has_permission(actor, permission)

    def require(self, actor: Actor, permission: str) -> None:
        """Raise ``PermissionError`` if the actor lacks the permission."""
        self._rbac.require(actor, permission)

    @property
    def approval_threshold(self) -> int:
        return self._threshold

    @approval_threshold.setter
    def approval_threshold(self, value: int) -> None:
        if not (0 <= value <= 100):
            raise ValueError("approval_threshold must be between 0 and 100")
        self._threshold = value
