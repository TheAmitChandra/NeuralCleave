"""Policy Engine — rule-based execution governance.

Every tool call passes through the ``PolicyEngine`` before execution.
The engine evaluates a stack of ``PolicyRule`` objects and returns a
``PolicyDecision`` that tells the caller whether to:

    - **allow**   — proceed immediately
    - **approve** — route to the human approval workflow
    - **deny**    — block with a reason

Built-in rules (evaluated top-to-bottom, first match wins):
    1. ``DenyBlockedTierRule``        — blocks anything with risk_score ≥ 86
    2. ``RequireApprovalForTier``     — approval for score 61–85
    3. ``TenantToolAllowlistRule``    — deny tools not on tenant allowlist (if configured)
    4. ``RateLimitRule``              — deny if actor has exceeded per-window call count
    5. ``TimeWindowRule``             — deny if outside permitted execution hours

Custom rules can be added at runtime via ``PolicyEngine.add_rule()``.

Usage::

    engine = PolicyEngine()
    decision = engine.evaluate(
        tool_name="shell.execute",
        risk_score=92,
        actor_id="agent-001",
        tenant_id="tenant-123",
    )
    if decision.action == PolicyAction.APPROVE:
        req = await approval_workflow.request_approval(...)
    elif decision.action == PolicyAction.DENY:
        raise PermissionError(decision.reason)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PolicyAction(str, Enum):
    ALLOW = "allow"
    APPROVE = "approve"   # route to human-approval workflow
    DENY = "deny"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PolicyContext:
    """Input context passed to every policy rule."""

    tool_name: str
    risk_score: int                   # 0–100
    actor_id: str
    tenant_id: str = "default"
    actor_permissions: list[str] = field(default_factory=list)
    tool_params: dict[str, Any] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyDecision:
    """Result of a policy evaluation.

    Attributes:
        action:       allow | approve | deny
        rule_name:    Name of the rule that matched.
        reason:       Human-readable explanation.
        risk_score:   Echoed from context for convenience.
        metadata:     Extra diagnostic info.
    """

    action: PolicyAction
    rule_name: str
    reason: str
    risk_score: int
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_allowed(self) -> bool:
        return self.action == PolicyAction.ALLOW

    @property
    def needs_approval(self) -> bool:
        return self.action == PolicyAction.APPROVE

    @property
    def is_denied(self) -> bool:
        return self.action == PolicyAction.DENY


# ---------------------------------------------------------------------------
# Abstract rule base
# ---------------------------------------------------------------------------

class PolicyRule(ABC):
    """Base class for all policy rules."""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        """Return a ``PolicyDecision`` if this rule matches, else ``None``."""
        ...


# ---------------------------------------------------------------------------
# Built-in rules
# ---------------------------------------------------------------------------

class DenyBlockedTierRule(PolicyRule):
    """Block any action with risk_score ≥ threshold (default 86).

    These are the ``isolated_container`` / ``blocked`` tier actions that
    *always* require a human decision first — they are denied here and the
    caller must route to the approval workflow explicitly.
    """

    def __init__(self, deny_threshold: int = 86) -> None:
        self._threshold = deny_threshold

    @property
    def name(self) -> str:
        return "deny_blocked_tier"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        if ctx.risk_score >= self._threshold:
            return PolicyDecision(
                action=PolicyAction.APPROVE,  # requires human approval, not outright deny
                rule_name=self.name,
                reason=(
                    f"Risk score {ctx.risk_score} ≥ threshold {self._threshold} "
                    f"— human approval required for {ctx.tool_name!r}"
                ),
                risk_score=ctx.risk_score,
            )
        return None


class RequireApprovalForHighRiskRule(PolicyRule):
    """Route to approval for medium-high risk range (default 61–85)."""

    def __init__(self, low: int = 61, high: int = 85) -> None:
        self._low = low
        self._high = high

    @property
    def name(self) -> str:
        return "require_approval_high_risk"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        if self._low <= ctx.risk_score <= self._high:
            return PolicyDecision(
                action=PolicyAction.APPROVE,
                rule_name=self.name,
                reason=(
                    f"Risk score {ctx.risk_score} in approval range "
                    f"[{self._low}, {self._high}] for {ctx.tool_name!r}"
                ),
                risk_score=ctx.risk_score,
            )
        return None


class TenantToolAllowlistRule(PolicyRule):
    """Deny tools not on a tenant-specific allowlist.

    If no allowlist is configured for a tenant, this rule passes.
    """

    def __init__(self, allowlists: dict[str, set[str]] | None = None) -> None:
        self._allowlists: dict[str, set[str]] = allowlists or {}

    @property
    def name(self) -> str:
        return "tenant_tool_allowlist"

    def set_allowlist(self, tenant_id: str, tools: set[str]) -> None:
        self._allowlists[tenant_id] = tools

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        tenant_list = self._allowlists.get(ctx.tenant_id)
        if tenant_list is None:
            return None  # no restriction configured
        if ctx.tool_name not in tenant_list:
            return PolicyDecision(
                action=PolicyAction.DENY,
                rule_name=self.name,
                reason=(
                    f"Tool {ctx.tool_name!r} not on allowlist for tenant {ctx.tenant_id!r}"
                ),
                risk_score=ctx.risk_score,
            )
        return None


class RateLimitRule(PolicyRule):
    """Deny actors exceeding a per-window call rate.

    Uses a sliding window (token bucket approach via a deque of timestamps).
    """

    def __init__(self, max_calls: int = 100, window_seconds: float = 60.0) -> None:
        self._max = max_calls
        self._window = window_seconds
        self._history: dict[str, deque[float]] = defaultdict(deque)

    @property
    def name(self) -> str:
        return "rate_limit"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        key = f"{ctx.tenant_id}:{ctx.actor_id}"
        now = time.monotonic()
        window_start = now - self._window
        dq = self._history[key]

        # Purge old entries
        while dq and dq[0] < window_start:
            dq.popleft()

        if len(dq) >= self._max:
            return PolicyDecision(
                action=PolicyAction.DENY,
                rule_name=self.name,
                reason=(
                    f"Actor {ctx.actor_id!r} exceeded {self._max} calls "
                    f"in {self._window}s window"
                ),
                risk_score=ctx.risk_score,
                metadata={"call_count": len(dq), "window_seconds": self._window},
            )

        dq.append(now)
        return None


class TimeWindowRule(PolicyRule):
    """Deny executions outside a permitted UTC hour range.

    Parameters:
        permitted_hours: Set of UTC hours (0–23) during which execution is allowed.
                         If ``None``, all hours are permitted.
    """

    def __init__(self, permitted_hours: set[int] | None = None) -> None:
        self._permitted = permitted_hours

    @property
    def name(self) -> str:
        return "time_window"

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        if self._permitted is None:
            return None
        import datetime as dt
        hour = dt.datetime.now(tz=dt.timezone.utc).hour
        if hour not in self._permitted:
            return PolicyDecision(
                action=PolicyAction.DENY,
                rule_name=self.name,
                reason=f"Execution not permitted at UTC hour {hour}",
                risk_score=ctx.risk_score,
                metadata={"current_hour_utc": hour, "permitted_hours": sorted(self._permitted)},
            )
        return None


class RequiredPermissionRule(PolicyRule):
    """Deny if actor lacks a required permission for the tool."""

    def __init__(self, tool_permission_map: dict[str, list[str]] | None = None) -> None:
        self._map: dict[str, list[str]] = tool_permission_map or {}

    @property
    def name(self) -> str:
        return "required_permission"

    def set_tool_permissions(self, tool_name: str, required: list[str]) -> None:
        self._map[tool_name] = required

    def evaluate(self, ctx: PolicyContext) -> PolicyDecision | None:
        required = self._map.get(ctx.tool_name, [])
        missing = [p for p in required if p not in ctx.actor_permissions]
        if missing:
            return PolicyDecision(
                action=PolicyAction.DENY,
                rule_name=self.name,
                reason=(
                    f"Actor {ctx.actor_id!r} missing permissions for {ctx.tool_name!r}: "
                    f"{missing}"
                ),
                risk_score=ctx.risk_score,
                metadata={"missing_permissions": missing},
            )
        return None


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

_DEFAULT_ALLOW = PolicyDecision(
    action=PolicyAction.ALLOW,
    rule_name="default",
    reason="No policy rule matched — action allowed",
    risk_score=0,
)


class PolicyEngine:
    """Evaluates a stack of ``PolicyRule`` objects against a ``PolicyContext``.

    Rules are evaluated in insertion order. The first rule to return a
    non-None decision wins (short-circuit). If no rule matches, the action
    defaults to ``ALLOW``.

    Parameters:
        use_defaults: If True, pre-load the built-in rule stack.
    """

    def __init__(self, use_defaults: bool = True) -> None:
        self._rules: list[PolicyRule] = []
        if use_defaults:
            self._rules = [
                DenyBlockedTierRule(),
                RequireApprovalForHighRiskRule(),
                RateLimitRule(),
            ]

    def add_rule(self, rule: PolicyRule, *, position: int | None = None) -> None:
        """Insert a rule. Optionally specify position (default: append)."""
        if position is None:
            self._rules.append(rule)
        else:
            self._rules.insert(position, rule)

    def remove_rule(self, rule_name: str) -> bool:
        """Remove the first rule with the given name. Returns True if removed."""
        for i, r in enumerate(self._rules):
            if r.name == rule_name:
                self._rules.pop(i)
                return True
        return False

    def evaluate(
        self,
        tool_name: str,
        risk_score: int,
        actor_id: str,
        tenant_id: str = "default",
        actor_permissions: list[str] | None = None,
        tool_params: dict[str, Any] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> PolicyDecision:
        """Run all rules against the provided context.

        Returns the first matching ``PolicyDecision`` or the default ALLOW.
        """
        ctx = PolicyContext(
            tool_name=tool_name,
            risk_score=risk_score,
            actor_id=actor_id,
            tenant_id=tenant_id,
            actor_permissions=actor_permissions or [],
            tool_params=tool_params or {},
            extra=extra or {},
        )

        for rule in self._rules:
            decision = rule.evaluate(ctx)
            if decision is not None:
                decision.risk_score = risk_score  # ensure echoed
                logger.info(
                    "policy.matched",
                    rule=rule.name,
                    action=decision.action.value,
                    tool_name=tool_name,
                    risk_score=risk_score,
                    actor_id=actor_id,
                )
                return decision

        # Default: allow
        default = PolicyDecision(
            action=PolicyAction.ALLOW,
            rule_name="default",
            reason="No policy rule matched — action allowed",
            risk_score=risk_score,
        )
        logger.debug(
            "policy.allowed_by_default",
            tool_name=tool_name,
            risk_score=risk_score,
            actor_id=actor_id,
        )
        return default

    @property
    def rule_names(self) -> list[str]:
        return [r.name for r in self._rules]
