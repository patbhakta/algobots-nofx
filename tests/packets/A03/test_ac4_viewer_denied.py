"""AC4: a viewer changing membership or posting a command is denied by policy,
and the attempt is recorded without secrets."""

import json
import uuid

import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.conftest import TEST_PASSWORD
from tests.packets.A03._helpers import make_member, make_owner, seed_workspace, unique_email

from algobots.api.database import get_session_factory
from algobots.api.models import AuditLog


def _deny_rows(user_id: str) -> list[AuditLog]:
    session = get_session_factory()()
    try:
        return list(
            session.scalars(
                sa.select(AuditLog).where(
                    AuditLog.method == "DENY", AuditLog.user_id == uuid.UUID(user_id)
                )
            )
        )
    finally:
        session.close()


def test_ac4_viewer_denied_and_attempts_audited_without_secrets(
    client: TestClient, founder_headers: dict
):
    owner = make_owner(client, founder_headers)
    rows = seed_workspace(client, owner["headers"])
    viewer = make_member(client, owner, "viewer")
    member = make_member(client, owner, "member")
    vh = viewer["headers"]
    secret_marker = f"tinv_should_never_be_logged_{TEST_PASSWORD}"

    invite_email = unique_email("x")
    attempts = [
        ("PATCH", f"/api/memberships/{member['membership_id']}", {"role": "owner"}),
        ("DELETE", f"/api/memberships/{member['membership_id']}", None),
        ("POST", "/api/memberships/invites", {"email": invite_email, "role": "member"}),
        (
            "POST",
            f"/api/memberships/{viewer['membership_id']}/grants",
            {"account_id": rows["account"], "grant": "TRADE_PAPER"},
        ),
        (
            "POST",
            "/api/orders",
            {"account_id": rows["account"], "symbol": "AAPL", "side": "buy", "qty": 1},
        ),
        ("PATCH", f"/api/orders/{rows['order']}", {"status": "cancelled"}),
        (
            "POST",
            "/api/accounts",
            {"label": secret_marker, "broker": "alpaca"},
        ),
    ]
    for method, path, body in attempts:
        response = client.request(method, path, headers=vh, json=body)
        assert response.status_code == 403, (method, path, response.text)

    # Nothing changed.
    memberships = {
        m["id"]: m for m in client.get("/api/memberships", headers=owner["headers"]).json()
    }
    assert memberships[member["membership_id"]]["role"] == "member"
    assert memberships[member["membership_id"]]["status"] == "active"
    assert (
        client.get(f"/api/orders/{rows['order']}", headers=owner["headers"]).json()["status"]
        != "cancelled"
    )
    invites = client.get("/api/memberships/invites", headers=owner["headers"]).json()
    assert invite_email not in {i["email"] for i in invites}

    denials = _deny_rows(viewer["user_id"])
    assert len(denials) == len(attempts)
    actions = {json.loads(d.detail_json)["action"] for d in denials}
    assert actions == {"membership.manage", "resource.write"}
    for row in denials:
        assert row.tenant_id == uuid.UUID(owner["tenant_id"])
        assert row.status_code == 403
        assert json.loads(row.detail_json)["role"] == "viewer"

    # No secrets anywhere in the audit trail: not the viewer's bearer token,
    # not the password, not the request body.
    session = get_session_factory()()
    try:
        everything = " ".join(
            f"{r.path} {r.detail_json} {r.resource} {r.resource_id}"
            for r in session.scalars(sa.select(AuditLog))
        )
    finally:
        session.close()
    assert viewer["token"] not in everything
    assert TEST_PASSWORD not in everything
    assert secret_marker not in everything


def test_ac4_viewer_can_read(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    rows = seed_workspace(client, owner["headers"])
    viewer = make_member(client, owner, "viewer")
    assert (
        client.get(f"/api/accounts/{rows['account']}", headers=viewer["headers"]).status_code == 200
    )
    assert client.get("/api/export", headers=viewer["headers"]).status_code == 200


def test_ac4_member_cannot_manage_memberships(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    member = make_member(client, owner, "member")
    response = client.post(
        "/api/memberships/invites",
        headers=member["headers"],
        json={"email": unique_email("y"), "role": "viewer"},
    )
    assert response.status_code == 403
    assert client.get("/api/memberships/invites", headers=member["headers"]).status_code == 403
