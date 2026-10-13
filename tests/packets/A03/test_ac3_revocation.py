"""AC3: a revoked member's old session is rejected on its next privileged
request, inside the declared revocation window.

Declared window: 0 s. Every authenticated request re-reads the `auth_sessions`
row and the active membership, so there is no cache to expire; the tests
assert rejection on the very next request and that it lands well under the 60 s
target.
"""

import time

from fastapi.testclient import TestClient
from tests.packets.A03._helpers import bearer, login, make_member, make_owner

REVOCATION_TARGET_S = 60.0


def _privileged(client: TestClient, headers: dict):
    return client.post(
        "/api/accounts", headers=headers, json={"label": f"x-{time.time_ns()}", "broker": "alpaca"}
    )


def test_ac3_revoked_member_old_session_rejected(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    member = make_member(client, owner, "member")
    assert _privileged(client, member["headers"]).status_code == 201

    revoked_at = time.monotonic()
    response = client.delete(
        f"/api/memberships/{member['membership_id']}", headers=owner["headers"]
    )
    assert response.status_code == 204

    rejected = _privileged(client, member["headers"])
    elapsed = time.monotonic() - revoked_at
    assert rejected.status_code == 401
    assert elapsed < REVOCATION_TARGET_S
    # Reads die too: the whole session is revoked, not just writes.
    assert client.get("/api/accounts", headers=member["headers"]).status_code == 401
    # A fresh login lands in no tenant: no workspace access at all.
    fresh = bearer(login(client, member["email"]))
    assert client.get("/api/me", headers=fresh).json()["tenant_id"] is None
    assert _privileged(client, fresh).status_code == 403


def test_ac3_revocation_is_audited(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    member = make_member(client, owner, "member")
    client.delete(f"/api/memberships/{member['membership_id']}", headers=owner["headers"])
    events = [
        r
        for r in client.get("/api/audit", headers=owner["headers"]).json()
        if r["method"] == "EVENT" and r["path"] == "membership.revoked"
    ]
    assert len(events) == 1
    detail = events[0]["detail_json"]
    assert detail["target_user_id"] == member["user_id"]
    assert detail["sessions_revoked"] >= 1


def test_ac3_demotion_applies_on_next_request(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    member = make_member(client, owner, "member")
    assert _privileged(client, member["headers"]).status_code == 201
    client.patch(
        f"/api/memberships/{member['membership_id']}",
        headers=owner["headers"],
        json={"role": "viewer"},
    )
    assert _privileged(client, member["headers"]).status_code == 403


def test_ac3_logout_revokes_token(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    assert client.post("/api/auth/logout", headers=owner["headers"]).status_code == 204
    assert client.get("/api/me", headers=owner["headers"]).status_code == 401


def test_ac3_last_owner_cannot_be_removed(client: TestClient, founder_headers: dict):
    owner = make_owner(client, founder_headers)
    memberships = client.get("/api/memberships", headers=owner["headers"]).json()
    mine = next(m for m in memberships if m["user_id"] == owner["user_id"])
    assert (
        client.delete(f"/api/memberships/{mine['id']}", headers=owner["headers"]).status_code == 409
    )
    demote = client.patch(
        f"/api/memberships/{mine['id']}", headers=owner["headers"], json={"role": "member"}
    )
    assert demote.status_code == 409


def test_ac3_concurrent_mutual_demotion_keeps_an_owner(client: TestClient, founder_headers: dict):
    """ALG-3183 finding 2: two owners demoting each other at once."""
    import threading

    from algobots.api.main import app

    def once() -> None:
        first = make_owner(client, founder_headers)
        second = make_member(client, first, "member")
        promoted = client.patch(
            f"/api/memberships/{second['membership_id']}",
            headers=first["headers"],
            json={"role": "owner"},
        )
        assert promoted.status_code == 200
        first_mid = next(
            m["id"]
            for m in client.get("/api/memberships", headers=first["headers"]).json()
            if m["user_id"] == first["user_id"]
        )
        barrier = threading.Barrier(2)
        statuses: list[int] = []

        def demote(headers: dict, membership_id: str) -> None:
            local = TestClient(app, raise_server_exceptions=False)
            barrier.wait()
            r = local.patch(
                f"/api/memberships/{membership_id}", headers=headers, json={"role": "member"}
            )
            statuses.append(r.status_code)

        threads = [
            threading.Thread(target=demote, args=(first["headers"], second["membership_id"])),
            threading.Thread(target=demote, args=(second["headers"], first_mid)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(statuses) == 2 and statuses.count(200) == 1, statuses
        assert all(s in (200, 403, 409) for s in statuses), statuses
        owners = [
            m
            for m in client.get(
                "/api/memberships",
                headers=bearer(login(client, first["email"])),
            ).json()
            if m["role"] == "owner" and m["status"] == "active"
        ]
        assert len(owners) == 1

    for _ in range(5):
        once()
