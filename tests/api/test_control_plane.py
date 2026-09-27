"""ALG-3078 acceptance tests: register → invite → login → CRUD, tenancy,
audit-on-every-mutation, and Alembic up/down cleanliness."""

import json
import logging
import uuid
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import inspect

from algobots.api.database import get_session_factory
from algobots.api.models import AuditLog
from tests.api.conftest import TEST_PASSWORD, _alembic_config

EXPECTED_TABLES = {
    "users",
    "invite_codes",
    "accounts",
    "account_credentials",
    "strategies",
    "deployments",
    "orders",
    "decisions",
    "clamp_events",
    "audit_log",
}


def _audit_rows() -> list[AuditLog]:
    session = get_session_factory()()
    try:
        return list(session.scalars(sa.select(AuditLog).order_by(AuditLog.created_at)))
    finally:
        session.close()


# --- registration & auth ---


def test_bootstrap_registration_creates_owner(client: TestClient, founder: dict):
    me = client.get("/api/users/me", headers={"Authorization": f"Bearer {founder['token']}"})
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == founder["email"]
    assert body["role"] == "owner"


def test_register_duplicate_email_conflicts(client: TestClient, founder_headers: dict):
    invite = client.post("/api/auth/invites", headers=founder_headers).json()
    response = client.post(
        "/api/auth/register",
        json={
            "email": "founder@example.com",
            "password": TEST_PASSWORD,
            "display_name": "Impostor",
            "invite_code": invite["code"],
        },
    )
    assert response.status_code == 409


def test_register_rejects_bad_invite(client: TestClient):
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"x-{uuid.uuid4().hex[:8]}@example.com",
            "password": TEST_PASSWORD,
            "display_name": "X",
            "invite_code": "NOT-A-REAL-CODE",
        },
    )
    assert response.status_code == 409


def test_invite_is_single_use(client: TestClient, founder_headers: dict):
    invite = client.post("/api/auth/invites", headers=founder_headers)
    assert invite.status_code == 201
    code = invite.json()["code"]
    first = client.post(
        "/api/auth/register",
        json={
            "email": f"a-{uuid.uuid4().hex[:8]}@example.com",
            "password": TEST_PASSWORD,
            "display_name": "A",
            "invite_code": code,
        },
    )
    assert first.status_code == 201
    second = client.post(
        "/api/auth/register",
        json={
            "email": f"b-{uuid.uuid4().hex[:8]}@example.com",
            "password": TEST_PASSWORD,
            "display_name": "B",
            "invite_code": code,
        },
    )
    assert second.status_code == 409


def test_login_wrong_password_rejected(client: TestClient, founder: dict):
    response = client.post(
        "/api/auth/login", json={"email": founder["email"], "password": "wrong-password"}
    )
    assert response.status_code == 401


def test_endpoints_require_token(client: TestClient):
    for path in ("/api/users/me", "/api/accounts", "/api/strategies", "/api/audit"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/accounts", json={}).status_code == 401


def test_invalid_token_rejected(client: TestClient):
    headers = {"Authorization": "Bearer not-a-jwt"}
    assert client.get("/api/users/me", headers=headers).status_code == 401


def test_invite_flow_creates_member(client: TestClient, member_headers: dict):
    me = client.get("/api/users/me", headers=member_headers)
    assert me.status_code == 200
    assert me.json()["role"] == "member"


# --- CRUD across resource tables ---


def _make_account(client: TestClient, headers: dict) -> dict:
    # Labels are unique per user as of S4.1 (migration 0002), and the founder
    # fixture is session-scoped — suffix to stay unique across tests.
    response = client.post(
        "/api/accounts",
        json={"label": f"Paper IBKR {uuid.uuid4().hex[:8]}", "broker": "ibkr", "mode": "paper"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_strategy(client: TestClient, headers: dict) -> dict:
    response = client.post(
        "/api/strategies",
        json={
            "name": "Mean reversion v1",
            "kind": "mean_reversion",
            "params": {"lookback": 20, "zscore": 2.5},
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_account_crud(client: TestClient, member_headers: dict):
    account = _make_account(client, member_headers)
    assert account["status"] == "active"
    assert (
        client.get(f"/api/accounts/{account['id']}", headers=member_headers).json()["label"]
        == account["label"]
    )
    patched = client.patch(
        f"/api/accounts/{account['id']}", json={"status": "paused"}, headers=member_headers
    )
    assert patched.status_code == 200 and patched.json()["status"] == "paused"
    listed = client.get("/api/accounts", headers=member_headers).json()
    assert [a["id"] for a in listed] == [account["id"]]
    deleted = client.delete(f"/api/accounts/{account['id']}", headers=member_headers)
    assert deleted.status_code == 204
    assert client.get(f"/api/accounts/{account['id']}", headers=member_headers).status_code == 404


def test_account_delete_blocked_by_dependents(client: TestClient, member_headers: dict):
    account = _make_account(client, member_headers)
    order = client.post(
        "/api/orders",
        json={"account_id": account["id"], "symbol": "AAPL", "side": "buy", "qty": 10},
        headers=member_headers,
    )
    assert order.status_code == 201
    assert (
        client.delete(f"/api/accounts/{account['id']}", headers=member_headers).status_code == 409
    )


def test_strategy_crud_roundtrip_params(client: TestClient, member_headers: dict):
    strategy = _make_strategy(client, member_headers)
    got = client.get(f"/api/strategies/{strategy['id']}", headers=member_headers)
    assert got.json()["params"] == {"lookback": 20, "zscore": 2.5}
    patched = client.patch(
        f"/api/strategies/{strategy['id']}",
        json={"params": {"lookback": 55}, "is_active": False},
        headers=member_headers,
    )
    assert patched.status_code == 200
    assert patched.json()["params"] == {"lookback": 55}
    assert patched.json()["is_active"] is False
    assert (
        client.delete(f"/api/strategies/{strategy['id']}", headers=member_headers).status_code
        == 204
    )


def test_deployment_lifecycle(client: TestClient, member_headers: dict):
    account = _make_account(client, member_headers)
    strategy = _make_strategy(client, member_headers)
    created = client.post(
        "/api/deployments",
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=member_headers,
    )
    assert created.status_code == 201
    deployment = created.json()
    assert deployment["status"] == "running"
    stopped = client.patch(
        f"/api/deployments/{deployment['id']}",
        json={"status": "stopped"},
        headers=member_headers,
    )
    assert stopped.status_code == 200 and stopped.json()["status"] == "stopped"


def test_order_create_update_delete(client: TestClient, member_headers: dict):
    account = _make_account(client, member_headers)
    order = client.post(
        "/api/orders",
        json={
            "account_id": account["id"],
            "symbol": "aapl",
            "side": "buy",
            "order_type": "limit",
            "qty": 5,
            "limit_price": 187.25,
        },
        headers=member_headers,
    )
    assert order.status_code == 201
    body = order.json()
    assert body["symbol"] == "AAPL" and body["status"] == "pending"
    filled = client.patch(
        f"/api/orders/{body['id']}", json={"status": "filled"}, headers=member_headers
    )
    assert filled.status_code == 200 and filled.json()["status"] == "filled"
    assert (
        client.delete(f"/api/orders/{body['id']}", headers=member_headers).status_code == 409
    )  # filled orders are immutable history


def test_decision_and_clamp_event_records(client: TestClient, member_headers: dict):
    account = _make_account(client, member_headers)
    strategy = _make_strategy(client, member_headers)
    deployment = client.post(
        "/api/deployments",
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=member_headers,
    ).json()
    decision = client.post(
        "/api/decisions",
        json={
            "strategy_id": strategy["id"],
            "deployment_id": deployment["id"],
            "symbol": "AAPL",
            "action": "buy",
            "confidence": 0.82,
            "rationale": "zscore -2.6 beyond threshold",
        },
        headers=member_headers,
    )
    assert decision.status_code == 201
    clamp = client.post(
        "/api/clamp-events",
        json={
            "deployment_id": deployment["id"],
            "clamp_kind": "max_gross_exposure",
            "old_value": 1.5,
            "new_value": 1.0,
            "reason": "daily loss limit tripped",
        },
        headers=member_headers,
    )
    assert clamp.status_code == 201
    decisions = client.get("/api/decisions", headers=member_headers).json()
    clamps = client.get("/api/clamp-events", headers=member_headers).json()
    assert [d["id"] for d in decisions] == [decision.json()["id"]]
    assert [c["id"] for c in clamps] == [clamp.json()["id"]]


def test_cross_tenant_references_rejected(
    client: TestClient, member_headers: dict, founder_headers: dict
):
    founder_account = _make_account(client, founder_headers)
    # Member cannot attach an order to the founder's account.
    response = client.post(
        "/api/orders",
        json={"account_id": founder_account["id"], "symbol": "TSLA", "side": "buy", "qty": 1},
        headers=member_headers,
    )
    assert response.status_code == 404


# --- tenancy isolation ---


def test_tenant_isolation(client: TestClient, member_headers: dict, founder_headers: dict):
    founder_account = _make_account(client, founder_headers)
    founder_strategy = _make_strategy(client, founder_headers)
    member_account = _make_account(client, member_headers)

    # Cross-tenant reads are indistinguishable from missing rows.
    assert (
        client.get(f"/api/accounts/{founder_account['id']}", headers=member_headers).status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/strategies/{founder_strategy['id']}",
            json={"is_active": False},
            headers=member_headers,
        ).status_code
        == 404
    )
    assert (
        client.delete(f"/api/accounts/{founder_account['id']}", headers=member_headers).status_code
        == 404
    )

    # Lists are scoped per tenant.
    member_ids = {a["id"] for a in client.get("/api/accounts", headers=member_headers).json()}
    founder_ids = {a["id"] for a in client.get("/api/accounts", headers=founder_headers).json()}
    assert member_account["id"] in member_ids
    assert founder_account["id"] not in member_ids
    assert founder_account["id"] in founder_ids
    assert member_account["id"] not in founder_ids


# --- audit: a row for every mutation ---


def test_audit_row_written_for_every_mutation(client: TestClient, member_headers: dict):
    before = len(_audit_rows())

    account = _make_account(client, member_headers)  # POST /api/accounts → 201
    strategy = _make_strategy(client, member_headers)  # POST /api/strategies → 201
    deployment = client.post(
        "/api/deployments",
        json={"strategy_id": strategy["id"], "account_id": account["id"]},
        headers=member_headers,
    ).json()  # POST /api/deployments → 201
    client.patch(
        f"/api/deployments/{deployment['id']}", json={"status": "paused"}, headers=member_headers
    )  # PATCH → 200
    client.delete(f"/api/deployments/{deployment['id']}", headers=member_headers)  # DELETE → 204

    rows = _audit_rows()[before:]
    assert len(rows) == 5, "exactly one audit row per mutating request"
    expected = {
        ("POST", "/api/accounts", "accounts", 201),
        ("POST", "/api/strategies", "strategies", 201),
        ("POST", "/api/deployments", "deployments", 201),
        ("PATCH", f"/api/deployments/{deployment['id']}", "deployments", 200),
        ("DELETE", f"/api/deployments/{deployment['id']}", "deployments", 204),
    }
    actual = {(r.method, r.path, r.resource, r.status_code) for r in rows}
    assert actual == expected
    for row in rows:
        assert row.user_id is not None
        assert row.resource_id is not None
    account_rows = [r for r in rows if r.path == "/api/accounts"]
    assert account_rows[0].resource_id == account["id"]


def test_failed_mutation_audited_without_actor(client: TestClient):
    before = len(_audit_rows())
    response = client.post(
        "/api/auth/register",
        json={
            "email": f"unauth-{uuid.uuid4().hex[:8]}@example.com",
            "password": TEST_PASSWORD,
            "display_name": "Ghost",
            "invite_code": "BOGUS-CODE",
        },
    )
    assert response.status_code == 409
    rows = _audit_rows()[before:]
    assert len(rows) == 1
    assert rows[0].method == "POST" and rows[0].status_code == 409
    assert rows[0].user_id is None


def test_audit_endpoint_scoped_to_tenant(
    client: TestClient, member_headers: dict, founder_headers: dict
):
    _make_account(client, founder_headers)
    _make_account(client, member_headers)
    member_rows = client.get("/api/audit", headers=member_headers).json()
    founder_rows = client.get("/api/audit", headers=founder_headers).json()
    member_paths = {r["path"] for r in member_rows}
    founder_paths = {r["path"] for r in founder_rows}
    assert "/api/accounts" in member_paths
    assert "/api/accounts" in founder_paths
    member_ids = {r["id"] for r in member_rows}
    founder_ids = {r["id"] for r in founder_rows}
    assert not member_ids & founder_ids, "audit rows must be tenant-scoped"


# --- observability: structured access log ---


def test_access_log_emits_json_with_request_id(client: TestClient, member_headers: dict, caplog):
    with caplog.at_level(logging.INFO, logger="algobots.api.access"):
        response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")
    records = [
        json.loads(r.getMessage())
        for r in caplog.records
        if r.name == "algobots.api.access" and r.getMessage().startswith("{")
    ]
    assert records, "expected at least one JSON access-log line"
    line = records[-1]
    assert line["event"] == "http"
    assert line["path"] == "/healthz" and line["status"] == 200
    assert {"request_id", "method", "duration_ms", "user_id"} <= set(line)
    assert line["request_id"] == response.headers["X-Request-Id"]


# --- migrations: up/down/up clean on a fresh database ---


def test_migrations_up_down_clean(tmp_path: Path):
    url = f"sqlite:///{tmp_path / 'migration-cycle.db'}"
    cfg = _alembic_config(url)

    def table_names() -> set[str]:
        engine = sa.create_engine(url)
        try:
            return set(inspect(engine).get_table_names())
        finally:
            engine.dispose()

    command.upgrade(cfg, "head")
    tables = table_names()
    assert EXPECTED_TABLES <= tables
    assert tables <= EXPECTED_TABLES | {"alembic_version"}

    command.downgrade(cfg, "base")
    # All domain tables gone; only alembic's own bookkeeping table remains.
    assert table_names() <= {"alembic_version"}

    command.upgrade(cfg, "head")
    assert EXPECTED_TABLES <= table_names()


# --- healthz smoke (S0.1 contract preserved) ---


def test_healthz_still_ok(client: TestClient):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
