"""Fleet breaker tenancy regression (ALG-3186, ALG-3184 finding 2).

The reviewer's probe, as a test: a fleet breaker reset under the caller's
PERSONAL tenant must never un-halt a deployment in tenant A — including when
the caller has been demoted to viewer (or revoked) in A. Trip/reset act on
the ACTIVE tenant's (tenant, user) row only, and `effective_state` folds the
breaker of the deployment's OWN account tenant. This is AC6 of the A11
packet ([ALG-3283](/ALG/issues/ALG-3283)).
"""

import uuid

from fastapi.testclient import TestClient

from tests.conftest import TEST_PASSWORD
from tests.packets.A03._helpers import bearer, invite, login, unique_email

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


def _new_user_with_personal_tenant(client: TestClient, founder_headers: dict) -> dict:
    """Platform-invite user: personal tenant (owner), session starts there."""
    code = client.post("/api/auth/invites", headers=founder_headers).json()["code"]
    email = unique_email("user")
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": "User",
            "invite_code": code,
        },
    )
    assert response.status_code == 201, response.text
    token = login(client, email)
    me = client.get("/api/me", headers=bearer(token)).json()
    return {
        "email": email,
        "token": token,
        "headers": bearer(token),
        "user_id": me["id"],
        "personal_tenant_id": me["tenant_id"],
    }


def _join_tenant(client: TestClient, owner: dict, user: dict, role: str = "member") -> str:
    """Redeem an owner invite; returns the membership id."""
    token = invite(client, owner, user["email"], role)["token"]
    response = client.post(
        "/api/memberships/invites/redeem", headers=user["headers"], json={"token": token}
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _owner_of_tenant(client: TestClient, founder_headers: dict, prefix: str) -> dict:
    code = client.post("/api/auth/invites", headers=founder_headers).json()["code"]
    email = unique_email(prefix)
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": prefix.title(),
            "invite_code": code,
        },
    )
    assert response.status_code == 201, response.text
    token = login(client, email)
    me = client.get("/api/me", headers=bearer(token)).json()
    return {
        "email": email,
        "token": token,
        "headers": bearer(token),
        "user_id": me["id"],
        "tenant_id": me["tenant_id"],
    }


def _seed_account_strategy(client: TestClient, headers: dict, label: str) -> tuple[str, str]:
    account = client.post(
        "/api/accounts", headers=headers, json={"label": label, "broker": "alpaca"}
    )
    assert account.status_code == 201, account.text
    strategy = client.post(
        "/api/strategies",
        headers=headers,
        json={
            "name": f"ma-cross-{uuid.uuid4().hex[:6]}",
            "kind": "condition_dsl",
            "params": DSL_PARAMS,
        },
    )
    assert strategy.status_code == 201, strategy.text
    return account.json()["id"], strategy.json()["id"]


def _deploy(client: TestClient, headers: dict, account_id: str, strategy_id: str) -> dict:
    response = client.post(
        "/api/deployments",
        headers=headers,
        json={
            "strategy_id": strategy_id,
            "account_id": account_id,
            "symbol": "AAPL",
            "max_order_value": "1000",
            "max_daily_loss": "100",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _fleet(client: TestClient, headers: dict, action: str):
    return client.post(
        "/api/deployments/fleet/breaker", headers=headers, json={"action": action}
    )


def _switch(client: TestClient, headers: dict, tenant_id: str) -> None:
    response = client.post(f"/api/tenants/{tenant_id}/switch", headers=headers)
    assert response.status_code == 200, response.text


def _state(client: TestClient, headers: dict, deployment_id: str) -> dict:
    response = client.get(f"/api/deployments/{deployment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_reset_in_personal_tenant_cannot_unhalt_tenant_a(client, founder_headers):
    """The exact ALG-3184 probe: demote D to viewer, reset from the personal
    tenant — tenant A's deployment must STAY halted."""
    owner = _owner_of_tenant(client, founder_headers, "owner")
    member_d = _new_user_with_personal_tenant(client, founder_headers)
    dh = member_d["headers"]
    tenant_a = owner["tenant_id"]

    # D joins tenant A as a member and switches their session there.
    _join_tenant(client, owner, member_d, "member")
    _switch(client, dh, tenant_a)

    # D (resource.write in A) deploys inside tenant A.
    account_a, strategy = _seed_account_strategy(client, dh, label="tenant-a-main")
    deployment_a = _deploy(client, dh, account_a, strategy)
    assert deployment_a["effective_state"] == "running"

    # D trips the fleet breaker under tenant A: the deployment halts.
    tripped = _fleet(client, dh, "trip")
    assert tripped.status_code == 200 and tripped.json()["state"] == "open"
    halted = _state(client, dh, deployment_a["id"])
    assert halted["effective_state"] == "halted"
    assert halted["halt_source"] == "fleet_breaker"

    # The owner demotes D to viewer in tenant A.
    memberships = client.get("/api/memberships", headers=owner["headers"]).json()
    membership_id = next(m["id"] for m in memberships if m["user_id"] == member_d["user_id"])
    demote = client.patch(
        f"/api/memberships/{membership_id}",
        headers=owner["headers"],
        json={"role": "viewer"},
    )
    assert demote.status_code == 200, demote.text

    # D switches to their personal tenant and resets the breaker there: 200,
    # but it acts on the PERSONAL (tenant, user) row — not tenant A's.
    _switch(client, dh, member_d["personal_tenant_id"])
    reset = _fleet(client, dh, "reset")
    assert reset.status_code == 200 and reset.json()["state"] == "closed"

    # Back in tenant A (viewer: reads allowed): the deployment is still
    # halted — the personal-tenant reset could not touch tenant A's breaker.
    _switch(client, dh, tenant_a)
    state = _state(client, dh, deployment_a["id"])
    assert state["effective_state"] == "halted", state
    assert state["halt_source"] == "fleet_breaker"

    # A reset attempt from tenant A itself is refused: D is a viewer now.
    denied = _fleet(client, dh, "reset")
    assert denied.status_code == 403, denied.text
    assert _state(client, dh, deployment_a["id"])["effective_state"] == "halted"


def test_trip_is_scoped_one_tenant_halt_does_not_cross(client, founder_headers):
    """The isolation cuts both ways: a trip under D's personal tenant halts
    only the personal-tenant deployment; tenant A's stays running."""
    owner = _owner_of_tenant(client, founder_headers, "owner2")
    member_d = _new_user_with_personal_tenant(client, founder_headers)
    dh = member_d["headers"]

    # Personal-tenant deployment first (session starts there).
    account_p, strategy_p = _seed_account_strategy(client, dh, label="personal-main")
    deployment_p = _deploy(client, dh, account_p, strategy_p)

    # Then a deployment inside tenant A.
    _join_tenant(client, owner, member_d, "member")
    _switch(client, dh, owner["tenant_id"])
    account_a, strategy_a = _seed_account_strategy(client, dh, label="tenant-a-main")
    deployment_a = _deploy(client, dh, account_a, strategy_a)

    # Trip under the personal tenant.
    _switch(client, dh, member_d["personal_tenant_id"])
    tripped = _fleet(client, dh, "trip")
    assert tripped.status_code == 200 and tripped.json()["state"] == "open"

    personal = _state(client, dh, deployment_p["id"])
    assert personal["effective_state"] == "halted"
    assert personal["halt_source"] == "fleet_breaker"

    # Tenant A's deployment (its account belongs to tenant A) is unaffected —
    # observed from a tenant-A session.
    _switch(client, dh, owner["tenant_id"])
    in_a = _state(client, dh, deployment_a["id"])
    assert in_a["effective_state"] == "running"
    assert in_a["halt_source"] is None

    # Reset under the personal tenant resumes only the personal deployment.
    _switch(client, dh, member_d["personal_tenant_id"])
    reset = _fleet(client, dh, "reset")
    assert reset.status_code == 200 and reset.json()["state"] == "closed"
    assert _state(client, dh, deployment_p["id"])["effective_state"] == "running"

    _switch(client, dh, owner["tenant_id"])
    assert _state(client, dh, deployment_a["id"])["effective_state"] == "running"


def test_fleet_state_endpoint_reports_active_tenant_row(client, founder_headers):
    """GET reports the ACTIVE tenant's breaker row, default closed."""
    owner = _owner_of_tenant(client, founder_headers, "owner3")
    member_d = _new_user_with_personal_tenant(client, founder_headers)
    dh = member_d["headers"]

    _join_tenant(client, owner, member_d, "member")
    _switch(client, dh, owner["tenant_id"])

    seen = client.get("/api/deployments/fleet/breaker", headers=dh)
    assert seen.status_code == 200
    assert seen.json()["state"] == "closed"

    assert _fleet(client, dh, "trip").json()["state"] == "open"
    assert client.get("/api/deployments/fleet/breaker", headers=dh).json()["state"] == "open"

    # Same user, personal tenant: a different row, still closed.
    _switch(client, dh, member_d["personal_tenant_id"])
    assert client.get("/api/deployments/fleet/breaker", headers=dh).json()["state"] == "closed"
