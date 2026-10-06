"""AC5: concurrent invite redemption creates one authorized membership;
revoked/expired invitations fail; a new member gains no implicit account
trading grant. Also: invite-only registration and hashed token storage.

The same race against PostgreSQL row locks is
`test_pg_rls.py::test_ac5_concurrent_redemption_postgres`.
"""

import hashlib
import threading
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.conftest import TEST_PASSWORD
from tests.packets.A03._helpers import (
    bearer,
    invite,
    login,
    make_member,
    make_owner,
    seed_workspace,
    unique_email,
)

from algobots.api.database import get_session_factory
from algobots.api.main import app
from algobots.api.memberships.models import TenantInvite, TenantMembership
from algobots.api.memberships.service import principal_for
from algobots.contracts.identity import Grant

RACERS = 8


def _register_platform_user(client: TestClient, founder_headers: dict, email: str) -> dict:
    code = client.post("/api/auth/invites", headers=founder_headers).json()["code"]
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": TEST_PASSWORD, "display_name": "R", "invite_code": code},
    )
    assert response.status_code == 201, response.text
    return bearer(login(client, email))


def _memberships(tenant_id: str, user_id: str) -> list[TenantMembership]:
    session = get_session_factory()()
    try:
        return list(
            session.scalars(
                sa.select(TenantMembership).where(
                    TenantMembership.tenant_id == uuid.UUID(tenant_id),
                    TenantMembership.user_id == uuid.UUID(user_id),
                )
            )
        )
    finally:
        session.close()


def test_ac5_concurrent_redemption_creates_one_membership(
    client: TestClient, founder_headers: dict
):
    owner = make_owner(client, founder_headers)
    email = unique_email("racer")
    headers = _register_platform_user(client, founder_headers, email)
    token = invite(client, owner, email)["token"]

    barrier = threading.Barrier(RACERS)
    statuses: list[int] = []
    lock = threading.Lock()

    def redeem() -> None:
        local = TestClient(app, raise_server_exceptions=False)
        barrier.wait()
        response = local.post(
            "/api/memberships/invites/redeem", headers=headers, json={"token": token}
        )
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=redeem) for _ in range(RACERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(statuses) == RACERS, "every racer must get a response"
    assert sorted(statuses) == [201] + [409] * (RACERS - 1)
    user_id = client.get("/api/me", headers=headers).json()["id"]
    assert len(_memberships(owner["tenant_id"], user_id)) == 1


def test_ac5_concurrent_registration_with_one_token(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    email = unique_email("signup")
    token = invite(client, owner, email)["token"]
    barrier = threading.Barrier(RACERS)
    statuses: list[int] = []
    lock = threading.Lock()

    def register() -> None:
        local = TestClient(app, raise_server_exceptions=False)
        barrier.wait()
        response = local.post(
            "/api/auth/register",
            json={
                "email": email,
                "password": TEST_PASSWORD,
                "display_name": "Signup",
                "tenant_invite_token": token,
            },
        )
        with lock:
            statuses.append(response.status_code)

    threads = [threading.Thread(target=register) for _ in range(RACERS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(statuses) == RACERS, "every racer must get a response"
    assert sorted(statuses) == [201] + [409] * (RACERS - 1)
    members = client.get("/api/memberships", headers=owner["headers"]).json()
    assert len(members) == 2  # owner + the one winner


def test_ac5_revoked_and_expired_invites_fail(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)

    revoked_email = unique_email("revoked")
    revoked = invite(client, owner, revoked_email)
    assert (
        client.delete(
            f"/api/memberships/invites/{revoked['id']}", headers=owner["headers"]
        ).status_code
        == 204
    )
    response = client.post(
        "/api/auth/register",
        json={
            "email": revoked_email,
            "password": TEST_PASSWORD,
            "display_name": "Revoked",
            "tenant_invite_token": revoked["token"],
        },
    )
    assert response.status_code == 409 and "revoked" in response.text.lower()

    expired_email = unique_email("expired")
    expired = invite(client, owner, expired_email)
    session = get_session_factory()()
    try:
        row = session.get(TenantInvite, uuid.UUID(expired["id"]))
        row.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
    response = client.post(
        "/api/auth/register",
        json={
            "email": expired_email,
            "password": TEST_PASSWORD,
            "display_name": "Expired",
            "tenant_invite_token": expired["token"],
        },
    )
    assert response.status_code == 409 and "expired" in response.text.lower()

    # Used once, never again.
    used_email = unique_email("used")
    used = invite(client, owner, used_email)
    body = {
        "email": used_email,
        "password": TEST_PASSWORD,
        "display_name": "Used",
        "tenant_invite_token": used["token"],
    }
    assert client.post("/api/auth/register", json=body).status_code == 201
    other_headers = _register_platform_user(client, founder_headers, unique_email("other"))
    again = client.post(
        "/api/memberships/invites/redeem", headers=other_headers, json={"token": used["token"]}
    )
    assert again.status_code == 409


def test_ac5_invite_bound_to_recipient(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    token = invite(client, owner, unique_email("intended"))["token"]
    intruder = _register_platform_user(client, founder_headers, unique_email("intruder"))
    response = client.post(
        "/api/memberships/invites/redeem", headers=intruder, json={"token": token}
    )
    assert response.status_code == 403
    register = client.post(
        "/api/auth/register",
        json={
            "email": unique_email("intruder2"),
            "password": TEST_PASSWORD,
            "display_name": "I",
            "tenant_invite_token": token,
        },
    )
    assert register.status_code == 403


def test_ac5_new_member_has_no_implicit_trading_grant(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    rows = seed_workspace(client, owner["headers"])
    member = make_member(client, owner, "member")

    me = client.get("/api/me", headers=member["headers"]).json()
    assert me["role"] == "member"
    assert me["grants"] == []
    assert (
        client.get(
            f"/api/memberships/{member['membership_id']}/grants", headers=owner["headers"]
        ).json()
        == []
    )
    session = get_session_factory()()
    try:
        principal = principal_for(
            session, uuid.UUID(member["user_id"]), uuid.UUID(member["tenant_id"])
        )
    finally:
        session.close()
    assert principal.grants == ()
    assert not principal.has(Grant.TRADE_PAPER) and not principal.has(Grant.TRADE_LIVE)

    # Grants are explicit, per account, audited, and viewers can't trade.
    added = client.post(
        f"/api/memberships/{member['membership_id']}/grants",
        headers=owner["headers"],
        json={"account_id": rows["account"], "grant": "TRADE_PAPER"},
    )
    assert added.status_code == 201
    assert client.get("/api/me", headers=member["headers"]).json()["grants"] == ["TRADE_PAPER"]
    viewer = make_member(client, owner, "viewer")
    refused = client.post(
        f"/api/memberships/{viewer['membership_id']}/grants",
        headers=owner["headers"],
        json={"account_id": rows["account"], "grant": "TRADE_PAPER"},
    )
    assert refused.status_code == 403
    build_only = client.post(
        f"/api/memberships/{member['membership_id']}/grants",
        headers=owner["headers"],
        json={"account_id": rows["account"], "grant": "REPO_WRITE"},
    )
    assert build_only.status_code == 422


def test_ac5_invite_token_stored_hashed_and_shown_once(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    email = unique_email("hashed")
    created = invite(client, owner, email)
    session = get_session_factory()()
    try:
        row = session.scalar(sa.select(TenantInvite).where(TenantInvite.email == email))
    finally:
        session.close()
    assert row.token_hash == hashlib.sha256(created["token"].encode()).hexdigest()
    assert created["token"] not in row.token_hash
    listed = client.get("/api/memberships/invites", headers=owner["headers"]).json()
    assert all("token" not in i for i in listed)


def test_ac5_public_registration_disabled(client: TestClient):
    email = unique_email("public")
    base = {"email": email, "password": TEST_PASSWORD, "display_name": "Public"}
    assert client.post("/api/auth/register", json=base).status_code == 422
    forged = client.post(
        "/api/auth/register", json={**base, "tenant_invite_token": "tinv_not-a-real-token"}
    )
    assert forged.status_code == 409
    both = client.post(
        "/api/auth/register",
        json={**base, "invite_code": "SOMECODE", "tenant_invite_token": "tinv_whatever"},
    )
    assert both.status_code == 422


def test_ac5_owner_role_not_invitable(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    response = client.post(
        "/api/memberships/invites",
        headers=owner["headers"],
        json={"email": unique_email("own"), "role": "owner"},
    )
    assert response.status_code == 422
