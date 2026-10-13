"""A03 demo: two identical-looking but isolated workspaces (``make demo-A03``).

Stands in for "open two browser sessions": two tenant owners on one app,
each seeding the same account label, strategy name and symbol, then each one's
view, cross-tenant guesses, a viewer denial and a revocation. It runs on a
throwaway migrated SQLite file with synthetic users only. No broker or IdP is
contacted.
"""

import os
import tempfile
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_TMP = Path(tempfile.mkdtemp(prefix="a03-demo-"))
os.environ["ALGOBOTS_DATABASE_URL"] = f"sqlite:///{_TMP / 'demo.db'}"
os.environ["ALGOBOTS_JWT_SECRET"] = "demo-jwt-secret-" + uuid.uuid4().hex
os.environ["ALGOBOTS_BOOTSTRAP_INVITE_CODE"] = "DEMO-BOOTSTRAP"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from algobots.api.database import get_session_factory  # noqa: E402
from algobots.api.main import app  # noqa: E402
from algobots.dashboard.auth import (  # noqa: E402
    render_tenant_switcher_html,
    tenant_switcher_snapshot,
)

PASSWORD = "demo-password-0123"
cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("sqlalchemy.url", os.environ["ALGOBOTS_DATABASE_URL"])
cfg.attributes["configure_logger"] = False
command.upgrade(cfg, "head")
client = TestClient(app)


def register(email: str, **invite) -> dict:
    body = {"email": email, "password": PASSWORD, "display_name": email.split("@")[0], **invite}
    response = client.post("/api/auth/register", json=body)
    assert response.status_code == 201, response.text
    token = client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).json()
    return {"Authorization": f"Bearer {token['access_token']}"}


founder = register("founder@example.com", invite_code="DEMO-BOOTSTRAP")
sessions = {}
for name in ("alice", "bob"):
    code = client.post("/api/auth/invites", headers=founder).json()["code"]
    sessions[name] = register(f"{name}@example.com", invite_code=code)

ids = {}
for name, headers in sessions.items():
    account = client.post(
        "/api/accounts", headers=headers, json={"label": "main", "broker": "alpaca"}
    ).json()
    client.post("/api/strategies", headers=headers, json={"name": "momentum", "kind": "trend"})
    client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account["id"], "symbol": "AAPL", "side": "buy", "qty": 1},
    )
    ids[name] = account["id"]

for name, headers in sessions.items():
    me = client.get("/api/me", headers=headers).json()
    accounts = client.get("/api/accounts", headers=headers).json()
    print(
        f"[{name}] tenant {me['tenant_id'][:8]} role={me['role']} grants={me['grants']} "
        f"accounts={[(a['label'], a['id'][:8]) for a in accounts]}"
    )
    session = get_session_factory()()
    try:
        snapshot = tenant_switcher_snapshot(
            session, uuid.UUID(me["id"]), uuid.UUID(me["tenant_id"])
        )
    finally:
        session.close()
    print(f"[{name}] switcher: {render_tenant_switcher_html(snapshot)[:120]}...")

for actor, other in (("alice", "bob"), ("bob", "alice")):
    h = sessions[actor]
    url = f"/api/accounts/{ids[other]}"
    print(
        f"[{actor} -> {other}'s account] GET {client.get(url, headers=h).status_code} "
        f"PATCH {client.patch(url, headers=h, json={'label': 'x'}).status_code} "
        f"DELETE {client.delete(url, headers=h).status_code} "
        f"export-leak={ids[other] in client.get('/api/export', headers=h).text}"
    )

invite = client.post(
    "/api/memberships/invites",
    headers=sessions["alice"],
    json={"email": "victor@example.com", "role": "viewer"},
).json()
viewer = register("victor@example.com", tenant_invite_token=invite["token"])
order = client.post(
    "/api/orders",
    headers=viewer,
    json={"account_id": ids["alice"], "symbol": "AAPL", "side": "buy", "qty": 1},
)
read = client.get("/api/accounts", headers=viewer).status_code
print(f"[viewer in alice's tenant] read accounts {read}, post order {order.status_code}")
reuse = client.post(
    "/api/auth/register",
    json={
        "email": "victor@example.com",
        "password": PASSWORD,
        "display_name": "again",
        "tenant_invite_token": invite["token"],
    },
)
print(f"[invite reuse] {reuse.status_code} {reuse.json()['detail']}")

victor = next(
    m
    for m in client.get("/api/memberships", headers=sessions["alice"]).json()
    if m["role"] == "viewer"
)
client.delete(f"/api/memberships/{victor['id']}", headers=sessions["alice"])
after = client.get("/api/accounts", headers=viewer).status_code
print(f"[revoked viewer, old session] GET /api/accounts -> {after}")
