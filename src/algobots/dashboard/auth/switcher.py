"""Tenant switcher + member list fragment (A03 checklist 2).

`tenant_switcher_snapshot` builds the data model behind the dashboard's
workspace switcher from the caller's *active* memberships only, plus the member
list of the active tenant. The HTML renderer turns it into an embeddable
fragment; switching posts to `/api/tenants/{id}/switch`, which re-checks the
membership server-side. Member-management controls render only for roles the
policy allows, but the API enforces the policy regardless of what is rendered.
No tokens, hashes or emails of other tenants ever enter a snapshot.
"""

import html
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.auth.policy import Action, is_allowed
from algobots.api.memberships.models import MembershipStatus, Tenant, TenantMembership
from algobots.api.models import User


def tenant_switcher_snapshot(
    db: Session, user_id: UUID, active_tenant_id: UUID | None
) -> dict[str, Any]:
    rows = db.execute(
        select(Tenant, TenantMembership.role)
        .join(TenantMembership, TenantMembership.tenant_id == Tenant.id)
        .where(
            TenantMembership.user_id == user_id,
            TenantMembership.status == MembershipStatus.ACTIVE,
        )
        .order_by(TenantMembership.created_at, Tenant.id)
    ).all()
    tenants = [
        {
            "id": str(tenant.id),
            "name": tenant.name,
            "role": role,
            "active": tenant.id == active_tenant_id,
        }
        for tenant, role in rows
    ]
    active_role = next((t["role"] for t in tenants if t["active"]), None)
    members: list[dict[str, Any]] = []
    if active_role is not None:
        for membership, display_name in db.execute(
            select(TenantMembership, User.display_name)
            .join(User, User.id == TenantMembership.user_id)
            .where(
                TenantMembership.tenant_id == active_tenant_id,
                TenantMembership.status == MembershipStatus.ACTIVE,
            )
            .order_by(TenantMembership.created_at)
        ).all():
            members.append(
                {
                    "membership_id": str(membership.id),
                    "display_name": display_name,
                    "role": membership.role,
                }
            )
    return {
        "tenants": tenants,
        "active_role": active_role,
        "can_manage_members": is_allowed(active_role, Action.MEMBERSHIP_MANAGE),
        "members": members,
    }


def render_tenant_switcher_html(snapshot: dict[str, Any]) -> str:
    """Render a switcher snapshot as an HTML fragment (dashboard embed)."""
    parts = ["<section class='tenant-switcher'>", "<h2>Workspace</h2>"]
    if not snapshot["tenants"]:
        parts.append("<p class='tenant-none'>No active workspace membership.</p>")
        parts.append("</section>")
        return "".join(parts)
    parts.append("<ul class='tenant-list'>")
    for tenant in snapshot["tenants"]:
        name = html.escape(tenant["name"])
        role = html.escape(tenant["role"])
        if tenant["active"]:
            parts.append(f"<li class='tenant-active'><strong>{name}</strong> · {role}</li>")
        else:
            action = f"/api/tenants/{html.escape(tenant['id'])}/switch"
            parts.append(
                f"<li><form method='post' action='{action}'>"
                f"<button type='submit'>{name}</button> · {role}</form></li>"
            )
    parts.append("</ul>")
    parts.append("<h3>Members</h3><table class='tenant-members'>")
    parts.append("<tr><th>Name</th><th>Role</th></tr>")
    for member in snapshot["members"]:
        parts.append(
            f"<tr><td>{html.escape(member['display_name'])}</td>"
            f"<td>{html.escape(member['role'])}</td></tr>"
        )
    parts.append("</table>")
    if snapshot["can_manage_members"]:
        parts.append("<p class='tenant-manage'><a href='#invite'>Invite a member</a></p>")
    parts.append("</section>")
    return "".join(parts)
