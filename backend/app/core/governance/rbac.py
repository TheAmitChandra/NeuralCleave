"""Role-Based Access Control (RBAC) — CortexFlow governance layer.

Roles
─────
    admin      — full platform access; can manage users, agents, policies
    developer  — create/manage agents and workflows; cannot manage users
    operator   — approve/reject approval requests; view all audit logs
    viewer     — read-only access to dashboards and logs
    auditor    — read audit logs only; no execution rights

Each role is associated with a frozen set of ``Permission`` scopes.
A ``RBACPolicy`` evaluates whether an actor (identified by role) has
the required permission for an action.

Usage::

    policy = RBACPolicy()
    if not policy.has_permission(role="developer", permission="agent:create"):
        raise PermissionError("Insufficient role")

    # Or check multiple permissions at once (all must pass)
    policy.require_all(role="viewer", permissions=["workflow:read", "tool:read"])
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import FrozenSet

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Role enum
# ---------------------------------------------------------------------------

class Role(str, Enum):
    ADMIN = "admin"
    DEVELOPER = "developer"
    OPERATOR = "operator"
    VIEWER = "viewer"
    AUDITOR = "auditor"


# ---------------------------------------------------------------------------
# Permission constants
# ---------------------------------------------------------------------------

class Permission(str, Enum):
    # Agent permissions
    AGENT_CREATE = "agent:create"
    AGENT_READ = "agent:read"
    AGENT_UPDATE = "agent:update"
    AGENT_DELETE = "agent:delete"
    AGENT_EXECUTE = "agent:execute"

    # Workflow permissions
    WORKFLOW_CREATE = "workflow:create"
    WORKFLOW_READ = "workflow:read"
    WORKFLOW_RUN = "workflow:run"
    WORKFLOW_PAUSE = "workflow:pause"
    WORKFLOW_DELETE = "workflow:delete"
    WORKFLOW_ROLLBACK = "workflow:rollback"

    # Tool permissions
    TOOL_READ = "tool:read"
    TOOL_EXECUTE = "tool:execute"
    TOOL_REGISTER = "tool:register"

    # Memory permissions
    MEMORY_READ = "memory:read"
    MEMORY_WRITE = "memory:write"
    MEMORY_DELETE = "memory:delete"

    # Approval permissions
    APPROVAL_REQUEST = "approval:request"
    APPROVAL_DECIDE = "approval:decide"
    APPROVAL_READ = "approval:read"

    # User management
    USER_CREATE = "user:create"
    USER_READ = "user:read"
    USER_UPDATE = "user:update"
    USER_DELETE = "user:delete"

    # Audit
    AUDIT_READ = "audit:read"
    AUDIT_EXPORT = "audit:export"

    # Policy management
    POLICY_READ = "policy:read"
    POLICY_WRITE = "policy:write"

    # Observability
    METRICS_READ = "metrics:read"
    TRACES_READ = "traces:read"


# ---------------------------------------------------------------------------
# Role → permission mapping
# ---------------------------------------------------------------------------

_ALL_PERMISSIONS: FrozenSet[str] = frozenset(p.value for p in Permission)

_ROLE_PERMISSIONS: dict[Role, FrozenSet[str]] = {
    Role.ADMIN: _ALL_PERMISSIONS,

    Role.DEVELOPER: frozenset({
        Permission.AGENT_CREATE, Permission.AGENT_READ,
        Permission.AGENT_UPDATE, Permission.AGENT_DELETE, Permission.AGENT_EXECUTE,
        Permission.WORKFLOW_CREATE, Permission.WORKFLOW_READ,
        Permission.WORKFLOW_RUN, Permission.WORKFLOW_PAUSE, Permission.WORKFLOW_DELETE,
        Permission.WORKFLOW_ROLLBACK,
        Permission.TOOL_READ, Permission.TOOL_EXECUTE, Permission.TOOL_REGISTER,
        Permission.MEMORY_READ, Permission.MEMORY_WRITE,
        Permission.APPROVAL_REQUEST, Permission.APPROVAL_READ,
        Permission.METRICS_READ, Permission.TRACES_READ,
        Permission.POLICY_READ,
        Permission.AUDIT_READ,
    }),

    Role.OPERATOR: frozenset({
        Permission.AGENT_READ, Permission.AGENT_EXECUTE,
        Permission.WORKFLOW_READ, Permission.WORKFLOW_RUN,
        Permission.WORKFLOW_PAUSE, Permission.WORKFLOW_ROLLBACK,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
        Permission.APPROVAL_REQUEST, Permission.APPROVAL_DECIDE, Permission.APPROVAL_READ,
        Permission.AUDIT_READ, Permission.AUDIT_EXPORT,
        Permission.METRICS_READ, Permission.TRACES_READ,
        Permission.POLICY_READ,
        Permission.USER_READ,
    }),

    Role.VIEWER: frozenset({
        Permission.AGENT_READ,
        Permission.WORKFLOW_READ,
        Permission.TOOL_READ,
        Permission.MEMORY_READ,
        Permission.APPROVAL_READ,
        Permission.AUDIT_READ,
        Permission.METRICS_READ,
        Permission.TRACES_READ,
        Permission.POLICY_READ,
        Permission.USER_READ,
    }),

    Role.AUDITOR: frozenset({
        Permission.AUDIT_READ,
        Permission.AUDIT_EXPORT,
    }),
}

# Convert Permission enum values to plain strings for storage
_ROLE_PERMISSION_STRINGS: dict[Role, FrozenSet[str]] = {
    role: frozenset(p.value if isinstance(p, Permission) else p for p in perms)
    for role, perms in _ROLE_PERMISSIONS.items()
}


# ---------------------------------------------------------------------------
# Actor data class
# ---------------------------------------------------------------------------

@dataclass
class Actor:
    """An authenticated principal with an assigned role.

    Attributes:
        actor_id:     Unique ID (user_id or agent_id).
        role:         Assigned role (determines base permissions).
        tenant_id:    Multi-tenant scope.
        extra_grants: Additional permissions beyond the role defaults.
        denials:      Permissions explicitly revoked (override extra_grants).
    """

    actor_id: str
    role: Role
    tenant_id: str = "default"
    extra_grants: FrozenSet[str] = field(default_factory=frozenset)
    denials: FrozenSet[str] = field(default_factory=frozenset)

    @property
    def effective_permissions(self) -> FrozenSet[str]:
        base = _ROLE_PERMISSION_STRINGS.get(self.role, frozenset())
        return (base | self.extra_grants) - self.denials


# ---------------------------------------------------------------------------
# RBAC Policy
# ---------------------------------------------------------------------------

class RBACPolicy:
    """Evaluates access control decisions for actors.

    Supports both role-level checks and actor-level overrides via
    ``extra_grants`` / ``denials`` on the ``Actor`` object.
    """

    # ------------------------------------------------------------------
    # Role-level checks (no actor instance needed)
    # ------------------------------------------------------------------

    @staticmethod
    def role_has_permission(role: Role, permission: str) -> bool:
        """Check if a role (without overrides) has a permission."""
        return permission in _ROLE_PERMISSION_STRINGS.get(role, frozenset())

    @staticmethod
    def role_permissions(role: Role) -> FrozenSet[str]:
        """Return the full permission set for a role."""
        return _ROLE_PERMISSION_STRINGS.get(role, frozenset())

    # ------------------------------------------------------------------
    # Actor-level checks
    # ------------------------------------------------------------------

    @staticmethod
    def has_permission(actor: Actor, permission: str) -> bool:
        """Return True if the actor has the given permission."""
        return permission in actor.effective_permissions

    @staticmethod
    def has_any(actor: Actor, permissions: list[str]) -> bool:
        """Return True if the actor has at least one of the permissions."""
        ep = actor.effective_permissions
        return any(p in ep for p in permissions)

    @staticmethod
    def has_all(actor: Actor, permissions: list[str]) -> bool:
        """Return True only if the actor has every listed permission."""
        ep = actor.effective_permissions
        return all(p in ep for p in permissions)

    @staticmethod
    def require(actor: Actor, permission: str) -> None:
        """Raise ``PermissionError`` if the actor lacks the permission."""
        if permission not in actor.effective_permissions:
            logger.warning(
                "rbac.denied",
                actor_id=actor.actor_id,
                role=actor.role.value,
                permission=permission,
            )
            raise PermissionError(
                f"Actor {actor.actor_id!r} (role={actor.role.value}) "
                f"lacks permission {permission!r}"
            )
        logger.debug(
            "rbac.allowed",
            actor_id=actor.actor_id,
            role=actor.role.value,
            permission=permission,
        )

    @staticmethod
    def require_all(actor: Actor, permissions: list[str]) -> None:
        """Raise ``PermissionError`` if the actor lacks any of the permissions."""
        missing = [p for p in permissions if p not in actor.effective_permissions]
        if missing:
            logger.warning(
                "rbac.denied_multiple",
                actor_id=actor.actor_id,
                role=actor.role.value,
                missing=missing,
            )
            raise PermissionError(
                f"Actor {actor.actor_id!r} (role={actor.role.value}) "
                f"lacks permissions: {missing}"
            )

    @staticmethod
    def require_role(actor: Actor, *allowed_roles: Role) -> None:
        """Raise ``PermissionError`` if actor's role is not in allowed_roles."""
        if actor.role not in allowed_roles:
            allowed_names = [r.value for r in allowed_roles]
            logger.warning(
                "rbac.wrong_role",
                actor_id=actor.actor_id,
                role=actor.role.value,
                allowed=allowed_names,
            )
            raise PermissionError(
                f"Actor {actor.actor_id!r} role {actor.role.value!r} not in "
                f"allowed roles: {allowed_names}"
            )
