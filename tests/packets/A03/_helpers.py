"""Shared A03 test helpers: tenant owners, tenant invites, members by role.

Tenant owners are registered through a platform invite from the session
founder, so each owner gets a fresh personal tenant (an isolated workspace).
Members join an owner's tenant only through a tenant invite token.
"""

import uuid

from fastapi.testclient import TestClient
from tests.conftest import TEST_PASSWORD


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient, email: str) -> str:
    response = client.post("/api/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}@example.com"


def make_owner(client: TestClient, founder_headers: dict, prefix: str = "owner") -> dict:
    """A new user with their own personal tenant (role owner)."""
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


def invite(client: TestClient, owner: dict, email: str, role: str = "member") -> dict:
    response = client.post(
        "/api/memberships/invites", headers=owner["headers"], json={"email": email, "role": role}
    )
    assert response.status_code == 201, response.text
    return response.json()


def make_member(client: TestClient, owner: dict, role: str = "member") -> dict:
    """A new user who registers with a tenant invite into `owner`'s tenant."""
    email = unique_email(role)
    token = invite(client, owner, email, role)["token"]
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": TEST_PASSWORD,
            "display_name": role.title(),
            "tenant_invite_token": token,
        },
    )
    assert response.status_code == 201, response.text
    access = login(client, email)
    me = client.get("/api/me", headers=bearer(access)).json()
    assert me["tenant_id"] == owner["tenant_id"]
    membership_id = next(
        m["id"]
        for m in client.get("/api/memberships", headers=owner["headers"]).json()
        if m["user_id"] == me["id"]
    )
    return {
        "email": email,
        "token": access,
        "headers": bearer(access),
        "user_id": me["id"],
        "tenant_id": me["tenant_id"],
        "membership_id": membership_id,
        "role": role,
    }


def seed_workspace(client: TestClient, headers: dict, label: str = "main") -> dict:
    """Identical-looking rows: same account label, strategy name and symbol."""
    account = client.post(
        "/api/accounts", headers=headers, json={"label": label, "broker": "alpaca", "mode": "paper"}
    )
    assert account.status_code == 201, account.text
    strategy = client.post(
        "/api/strategies", headers=headers, json={"name": "momentum", "kind": "trend"}
    )
    assert strategy.status_code == 201, strategy.text
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account.json()["id"], "symbol": "AAPL", "side": "buy", "qty": 1},
    )
    assert order.status_code == 201, order.text
    decision = client.post(
        "/api/decisions",
        headers=headers,
        json={"strategy_id": strategy.json()["id"], "symbol": "AAPL", "action": "buy"},
    )
    assert decision.status_code == 201, decision.text
    clamp = client.post(
        "/api/clamp-events",
        headers=headers,
        json={"account_id": account.json()["id"], "clamp_kind": "exposure_cap", "reason": "x"},
    )
    assert clamp.status_code == 201, clamp.text
    return {
        "account": account.json()["id"],
        "strategy": strategy.json()["id"],
        "order": order.json()["id"],
        "decision": decision.json()["id"],
        "clamp": clamp.json()["id"],
    }
