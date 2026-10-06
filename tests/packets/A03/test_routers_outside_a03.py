"""AC3/AC4 for routers outside the A03 write scope (ALG-3183 finding 1).

Deployments, account credentials and approvals still authorize by `user_id`
in their own code. A03 closes the gap without editing them:
`get_current_user` requires an active membership and applies the role matrix
by method, and ORM criteria narrow their tables to the active tenant. These
are the reviewer's probe cases, made permanent.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.packets.A03._helpers import bearer, invite, login, make_member, make_owner

from algobots.api.accounts.models import AccountCredential
from algobots.api.approvals.models import ApprovalRequest
from algobots.api.database import get_session_factory
from algobots.api.deployments.models import Deployment

DSL_PARAMS = {
    "version": 1,
    "cadence": "5m",
    "entry": {
        "left": {"indicator": "sma", "params": {"period": 2}},
        "op": "crosses_above",
        "right": {"indicator": "sma", "params": {"period": 3}},
    },
    "exit": {
        "left": {"indicator": "sma", "params": {"period": 2}},
        "op": "crosses_below",
        "right": {"indicator": "sma", "params": {"period": 3}},
    },
}
CREDS = {"api_key": "probe-key-0123456789", "api_secret": "probe-secret-0123456789"}


def _workspace_rows(client: TestClient, headers: dict) -> dict:
    """A deployment, a semi-auto account with a parked approval: written by `headers`."""
    strategy = client.post(
        "/api/strategies",
        headers=headers,
        json={"name": "MA", "kind": "condition_dsl", "params": DSL_PARAMS},
    ).json()
    account = client.post(
        "/api/accounts",
        headers=headers,
        json={"label": "semi", "broker": "alpaca", "mode": "semi_auto"},
    ).json()
    deployment = client.post(
        "/api/deployments",
        headers=headers,
        json={
            "strategy_id": strategy["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "1000.00",
            "max_daily_loss": "500.00",
        },
    )
    assert deployment.status_code == 201, deployment.text
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account["id"], "symbol": "AAPL", "side": "buy", "qty": 1},
    )
    assert order.status_code == 201, order.text
    return {
        "account": account["id"],
        "deployment": deployment.json()["id"],
        "approval": order.headers["X-Approval-Request-Id"],
    }


def _attempts(rows: dict) -> list[tuple[str, str, dict | None]]:
    return [
        ("PATCH", f"/api/deployments/{rows['deployment']}", {"status": "paused"}),
        ("PUT", f"/api/accounts/{rows['account']}/credentials", CREDS),
        (
            "POST",
            f"/api/approvals/{rows['approval']}/decide",
            {"verdict": "approved", "reason": "x"},
        ),
    ]


def _assert_untouched(rows: dict) -> None:
    """Read state straight from the DB (an unscoped session): deployments and
    approvals are still visible only to the user who wrote them, so the owner's
    API view can't confirm this."""
    session = get_session_factory()()
    try:
        deployment = session.get(Deployment, uuid.UUID(rows["deployment"]))
        assert deployment.status != "paused"
        assert (
            session.scalar(
                select(AccountCredential).where(
                    AccountCredential.account_id == uuid.UUID(rows["account"])
                )
            )
            is None
        )
        assert session.get(ApprovalRequest, uuid.UUID(rows["approval"])).status == "parked"
    finally:
        session.close()


@pytest.fixture()
def workspace(client: TestClient, founder_headers: dict) -> dict:
    owner = make_owner(client, founder_headers)
    member = make_member(client, owner, "member")
    rows = _workspace_rows(client, member["headers"])  # written by the member
    return {"owner": owner, "member": member, "rows": rows}


def test_revoked_member_new_session_cannot_use_other_routers(client: TestClient, workspace: dict):
    owner, member, rows = workspace["owner"], workspace["member"], workspace["rows"]
    client.delete(f"/api/memberships/{member['membership_id']}", headers=owner["headers"])
    fresh = bearer(login(client, member["email"]))
    assert client.get("/api/me", headers=fresh).json()["tenants"] == []
    assert client.get("/api/deployments", headers=fresh).status_code == 403
    assert client.get("/api/approvals", headers=fresh).status_code == 403
    for method, path, body in _attempts(rows):
        assert client.request(method, path, headers=fresh, json=body).status_code == 403, path
    _assert_untouched(rows)


def test_viewer_cannot_mutate_through_other_routers(client: TestClient, workspace: dict):
    owner, member, rows = workspace["owner"], workspace["member"], workspace["rows"]
    client.patch(
        f"/api/memberships/{member['membership_id']}",
        headers=owner["headers"],
        json={"role": "viewer"},
    )
    h = member["headers"]
    assert client.get("/api/deployments", headers=h).status_code == 200  # reads still allowed
    for method, path, body in [
        *_attempts(rows),
        ("POST", "/api/deployments/fleet/breaker", {"state": "open", "reason": "x"}),
        ("POST", "/api/accounts/token-sweep", None),
    ]:
        response = client.request(method, path, headers=h, json=body)
        assert response.status_code == 403, (path, response.text)
    _assert_untouched(rows)
    denials = [
        r
        for r in client.get("/api/audit", headers=owner["headers"]).json()
        if r["method"] == "DENY"
    ]
    assert len(denials) >= 5
    assert all(r["detail_json"]["action"] == "resource.write" for r in denials)


def test_member_of_two_tenants_cannot_reach_rows_across_them(
    client: TestClient, founder_headers: dict
):
    """A user with their own personal tenant who also joins tenant A."""
    owner = make_owner(client, founder_headers, "tenant-a")
    dual = make_owner(client, founder_headers, "dual")  # personal tenant = their own
    token = invite(client, owner, dual["email"], "member")["token"]
    assert (
        client.post(
            "/api/memberships/invites/redeem", headers=dual["headers"], json={"token": token}
        ).status_code
        == 201
    )
    assert (
        client.post(
            f"/api/tenants/{owner['tenant_id']}/switch", headers=dual["headers"]
        ).status_code
        == 200
    )
    rows = _workspace_rows(client, dual["headers"])  # written in tenant A by `dual`

    # Back in their personal tenant: tenant A's rows don't exist for them.
    personal = bearer(login(client, dual["email"]))
    assert client.get("/api/me", headers=personal).json()["tenant_id"] == dual["tenant_id"]
    listed = client.get("/api/deployments", headers=personal)
    assert listed.status_code == 200 and rows["deployment"] not in listed.text
    assert rows["approval"] not in client.get("/api/approvals", headers=personal).text
    assert client.get(f"/api/deployments/{rows['deployment']}", headers=personal).status_code == 404
    assert client.get(f"/api/approvals/{rows['approval']}", headers=personal).status_code == 404
    for method, path, body in _attempts(rows):
        response = client.request(method, path, headers=personal, json=body)
        assert response.status_code == 404, (path, response.text)
    _assert_untouched(rows)

    # And after revocation from A, nothing changes for the personal session.
    memberships = client.get("/api/memberships", headers=owner["headers"]).json()
    dual_membership = next(m for m in memberships if m["user_id"] == dual["user_id"])
    client.delete(f"/api/memberships/{dual_membership['id']}", headers=owner["headers"])
    personal = bearer(login(client, dual["email"]))
    for method, path, body in _attempts(rows):
        assert client.request(method, path, headers=personal, json=body).status_code == 404
    _assert_untouched(rows)
