"""Tenant role matrix (A03 checklist 2).

Workspace membership and account trading grants are separate axes: a role
says what a member may do *in the workspace*; trading authority on a broker
account exists only as an explicit `account_grants` row (see
`algobots.api.memberships.service.principal_for`). No role implies a grant.

Unknown roles and unknown actions are denied (default deny).
"""

from enum import StrEnum


class TenantRole(StrEnum):
    OWNER = "owner"
    MEMBER = "member"
    VIEWER = "viewer"


class Action(StrEnum):
    TENANT_READ = "tenant.read"  # list/read/export tenant-owned rows
    RESOURCE_WRITE = "resource.write"  # create/update/delete rows, post commands
    MEMBERSHIP_MANAGE = "membership.manage"  # invite, change role, revoke, grants
    AUDIT_READ_ALL = "audit.read_all"  # every tenant audit row, not just one's own


ROLE_MATRIX: dict[TenantRole, frozenset[Action]] = {
    TenantRole.OWNER: frozenset(Action),
    TenantRole.MEMBER: frozenset({Action.TENANT_READ, Action.RESOURCE_WRITE}),
    TenantRole.VIEWER: frozenset({Action.TENANT_READ}),
}

# Roles an invite may confer. Ownership is never handed out by invitation;
# an owner promotes an existing member explicitly (audited).
INVITABLE_ROLES = frozenset({TenantRole.MEMBER, TenantRole.VIEWER})


def is_allowed(role: str | None, action: Action) -> bool:
    """True only for a known role whose matrix row contains the action."""
    try:
        return action in ROLE_MATRIX[TenantRole(role)]
    except ValueError:
        return False
