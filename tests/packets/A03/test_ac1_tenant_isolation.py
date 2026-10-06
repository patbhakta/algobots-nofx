"""AC1: tenants A and B with overlapping labels; A guesses B's ids through
read/write/list/export endpoints; every attempt is denied and no B data appears.

This module is the application-layer half (runs on the SQLite test DB). The
database-layer half, PostgreSQL row-level policies under a non-bypass role, is
`test_pg_rls.py::test_ac1_rls_*`.
"""

import json

import pytest
from fastapi.testclient import TestClient
from tests.packets.A03._helpers import make_member, make_owner, seed_workspace

RESOURCES = {
    "account": "/api/accounts",
    "strategy": "/api/strategies",
    "order": "/api/orders",
}


@pytest.fixture()
def two_tenants(client: TestClient, founder_headers: dict) -> dict:
    a = make_owner(client, founder_headers, "tenant-a")
    b = make_owner(client, founder_headers, "tenant-b")
    a_member = make_member(client, a, "member")
    return {
        "a": a,
        "b": b,
        "a_member": a_member,
        "a_rows": seed_workspace(client, a["headers"]),
        "b_rows": seed_workspace(client, b["headers"]),
    }


def _b_ids(t: dict) -> set[str]:
    return set(t["b_rows"].values())


def test_ac1_guessed_ids_denied_on_read_write_delete(client: TestClient, two_tenants: dict):
    b_rows = two_tenants["b_rows"]
    for actor in ("a", "a_member"):
        headers = two_tenants[actor]["headers"]
        for kind, base in RESOURCES.items():
            url = f"{base}/{b_rows[kind]}"
            assert client.get(url, headers=headers).status_code == 404
            patch_body = {"status": "cancelled"} if kind == "order" else {"label": "pwned"}
            if kind == "strategy":
                patch_body = {"name": "pwned"}
            assert client.patch(url, headers=headers, json=patch_body).status_code == 404
            assert client.delete(url, headers=headers).status_code == 404

    # B's rows are untouched.
    b_headers = two_tenants["b"]["headers"]
    assert (
        client.get(f"/api/accounts/{b_rows['account']}", headers=b_headers).json()["label"]
        == "main"
    )
    assert (
        client.get(f"/api/strategies/{b_rows['strategy']}", headers=b_headers).json()["name"]
        == "momentum"
    )
    assert client.get(f"/api/orders/{b_rows['order']}", headers=b_headers).json()["status"] != (
        "cancelled"
    )


def test_ac1_cannot_attach_rows_to_other_tenant_parents(client: TestClient, two_tenants: dict):
    headers = two_tenants["a"]["headers"]
    b_rows = two_tenants["b_rows"]
    order = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": b_rows["account"], "symbol": "AAPL", "side": "buy", "qty": 1},
    )
    assert order.status_code == 404
    decision = client.post(
        "/api/decisions",
        headers=headers,
        json={"strategy_id": b_rows["strategy"], "symbol": "AAPL", "action": "buy"},
    )
    assert decision.status_code == 404
    clamp = client.post(
        "/api/clamp-events",
        headers=headers,
        json={"account_id": b_rows["account"], "clamp_kind": "exposure_cap"},
    )
    assert clamp.status_code == 404


def test_ac1_lists_and_export_contain_no_other_tenant_data(client: TestClient, two_tenants: dict):
    b_ids = _b_ids(two_tenants)
    b_tenant = two_tenants["b"]["tenant_id"]
    for actor in ("a", "a_member"):
        headers = two_tenants[actor]["headers"]
        for path in (
            "/api/accounts",
            "/api/strategies",
            "/api/orders",
            "/api/decisions",
            "/api/clamp-events",
            "/api/memberships",
            "/api/audit",
        ):
            response = client.get(path, headers=headers)
            assert response.status_code == 200, path
            body = response.text
            assert not any(i in body for i in b_ids), path
            assert b_tenant not in body, path
        export = client.get("/api/export", headers=headers)
        assert export.status_code == 200
        dump = json.dumps(export.json())
        assert export.json()["tenant_id"] == two_tenants["a"]["tenant_id"]
        assert not any(i in dump for i in b_ids)
        assert b_tenant not in dump
        # A's own identical-looking rows are all there.
        assert {r["id"] for r in export.json()["accounts"]} >= {two_tenants["a_rows"]["account"]}


def test_ac1_member_sees_shared_tenant_rows(client: TestClient, two_tenants: dict):
    """Isolation is by tenant, not by user: A's member sees A's rows."""
    rows = client.get("/api/accounts", headers=two_tenants["a_member"]["headers"]).json()
    assert two_tenants["a_rows"]["account"] in {r["id"] for r in rows}


def test_ac1_cursor_from_other_tenant_rejected(client: TestClient, two_tenants: dict):
    b_headers = two_tenants["b"]["headers"]
    seed_workspace(client, b_headers, label="second")
    page = client.get("/api/accounts?limit=1", headers=b_headers)
    assert page.status_code == 200 and len(page.json()) == 1
    cursor = page.headers["X-Next-Cursor"]
    # B can follow its own cursor...
    follow = client.get(f"/api/accounts?limit=1&cursor={cursor}", headers=b_headers)
    assert follow.status_code == 200 and len(follow.json()) == 1
    # ...A cannot use it, and a tampered cursor is rejected too.
    stolen = client.get(f"/api/accounts?cursor={cursor}", headers=two_tenants["a"]["headers"])
    assert stolen.status_code == 400
    forged = cursor[:-4] + ("AAAA" if not cursor.endswith("AAAA") else "BBBB")
    assert client.get(f"/api/accounts?cursor={forged}", headers=b_headers).status_code == 400


def test_ac1_switch_to_non_member_tenant_denied(client: TestClient, two_tenants: dict):
    a = two_tenants["a"]
    response = client.post(
        f"/api/tenants/{two_tenants['b']['tenant_id']}/switch", headers=a["headers"]
    )
    assert response.status_code == 404
    assert client.get("/api/me", headers=a["headers"]).json()["tenant_id"] == a["tenant_id"]


def test_ac1_membership_management_cannot_target_other_tenant(
    client: TestClient, two_tenants: dict, founder_headers: dict
):
    b_member = make_member(client, two_tenants["b"], "member")
    a_headers = two_tenants["a"]["headers"]
    url = f"/api/memberships/{b_member['membership_id']}"
    assert client.patch(url, headers=a_headers, json={"role": "viewer"}).status_code == 404
    assert client.delete(url, headers=a_headers).status_code == 404
    grant = client.post(
        f"/api/memberships/{two_tenants['a_member']['membership_id']}/grants",
        headers=a_headers,
        json={"account_id": two_tenants["b_rows"]["account"], "grant": "ACCOUNT_READ"},
    )
    assert grant.status_code == 404
