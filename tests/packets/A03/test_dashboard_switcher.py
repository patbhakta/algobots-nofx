"""Tenant switcher fragment: own active memberships only; switching is
membership-checked server-side."""

import uuid

from fastapi.testclient import TestClient
from tests.conftest import TEST_PASSWORD
from tests.packets.A03._helpers import (
    bearer,
    invite,
    login,
    make_owner,
)

from algobots.api.database import get_session_factory
from algobots.dashboard.auth import render_tenant_switcher_html, tenant_switcher_snapshot


def _snapshot(me: dict) -> dict:
    session = get_session_factory()()
    try:
        return tenant_switcher_snapshot(
            session, uuid.UUID(me["id"]), me["tenant_id"] and uuid.UUID(me["tenant_id"])
        )
    finally:
        session.close()


def test_switcher_lists_memberships_and_switch_changes_context(
    client: TestClient, founder_headers: dict
):
    a = make_owner(client, founder_headers, "sw-a")
    b = make_owner(client, founder_headers, "sw-b")
    # B's owner also joins A's tenant as a viewer.
    token = invite(client, a, b["email"], "viewer")["token"]
    redeemed = client.post(
        "/api/memberships/invites/redeem", headers=b["headers"], json={"token": token}
    )
    assert redeemed.status_code == 201

    me = client.get("/api/me", headers=b["headers"]).json()
    snap = _snapshot(me)
    assert {t["id"] for t in snap["tenants"]} == {a["tenant_id"], b["tenant_id"]}
    assert snap["can_manage_members"] is True  # owner of own tenant
    html = render_tenant_switcher_html(snap)
    assert f"/api/tenants/{a['tenant_id']}/switch" in html

    switched = client.post(f"/api/tenants/{a['tenant_id']}/switch", headers=b["headers"])
    assert switched.status_code == 200 and switched.json()["role"] == "viewer"
    me = client.get("/api/me", headers=b["headers"]).json()
    assert me["tenant_id"] == a["tenant_id"] and me["role"] == "viewer"
    snap = _snapshot(me)
    assert snap["can_manage_members"] is False
    assert "Invite a member" not in render_tenant_switcher_html(snap)
    # The switch is per session: a fresh login starts in the personal tenant.
    fresh = client.get("/api/me", headers=bearer(login(client, b["email"]))).json()
    assert fresh["tenant_id"] == b["tenant_id"]
    assert TEST_PASSWORD not in html


def test_switcher_escapes_names(client: TestClient, founder_headers: dict):
    snap = {
        "tenants": [{"id": "x", "name": "<script>", "role": "owner", "active": True}],
        "active_role": "owner",
        "can_manage_members": True,
        "members": [{"membership_id": "m", "display_name": "<b>", "role": "owner"}],
    }
    html = render_tenant_switcher_html(snap)
    assert "<script>" not in html and "&lt;script&gt;" in html
