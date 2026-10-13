"""A04 demo: four mock accounts, one rotation, per-account status (``make demo-A04``).

Stands in for the founder demo scene: a tenant connects four mock venue
accounts across two environments, rotates one credential, and the registry
view shows per-account session state, secret version and reconciliation
posture — with the rotated account keeping a single ownership record. Runs on
a throwaway migrated SQLite file with synthetic users only. No broker or IdP
is contacted.
"""

import os
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
_TMP = Path(tempfile.mkdtemp(prefix="a04-demo-"))
os.environ["ALGOBOTS_DATABASE_URL"] = f"sqlite:///{_TMP / 'demo.db'}"
os.environ["ALGOBOTS_JWT_SECRET"] = "demo-jwt-secret-" + uuid.uuid4().hex
os.environ["ALGOBOTS_BOOTSTRAP_INVITE_CODE"] = "DEMO-BOOTSTRAP"
os.environ["ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY"] = (
    __import__("cryptography.fernet", fromlist=["Fernet"]).Fernet.generate_key().decode()
)

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from algobots.api.main import app  # noqa: E402

PASSWORD = "demo-password-0123"
FRESH = (datetime.now(UTC) + timedelta(hours=6)).isoformat()

cfg = Config(str(ROOT / "alembic.ini"))
cfg.set_main_option("sqlalchemy.url", os.environ["ALGOBOTS_DATABASE_URL"])
cfg.attributes["configure_logger"] = False
command.upgrade(cfg, "head")
client = TestClient(app)

registered = client.post(
    "/api/auth/register",
    json={
        "email": "a04-founder@example.com",
        "password": PASSWORD,
        "display_name": "A04 Founder",
        "invite_code": "DEMO-BOOTSTRAP",
    },
)
assert registered.status_code == 201, registered.text
token = client.post(
    "/api/auth/login", json={"email": "a04-founder@example.com", "password": PASSWORD}
).json()["access_token"]
headers = {"Authorization": f"Bearer {token}"}

ACCOUNTS = [
    ("Mock alpha", "ext-demo-001", "synthetic-paper", "USD"),
    ("Mock beta", "ext-demo-002", "synthetic-paper", "EUR"),
    ("Mock gamma", "ext-demo-003", "development", "USD"),
    ("Mock delta", "ext-demo-004", "synthetic-paper", "USD"),
]

onboarded = []
for label, external_id, environment, currency in ACCOUNTS:
    response = client.post(
        "/api/broker-accounts",
        headers=headers,
        json={
            "label": label,
            "provider": "mock",
            "environment": environment,
            "external_account_id": external_id,
            "base_currency": currency,
            "credentials": {
                "api_key": f"ak-demo-SECRET-{external_id[-3:]}",
                "api_secret": f"as-demo-SECRET-{external_id[-3:]}",
                "token_expires_at": FRESH,
            },
        },
    )
    assert response.status_code == 201, response.text
    onboarded.append(response.json())

print("== onboarding: four mock accounts, distinct identities and environment labels ==")
for row in onboarded:
    conn = row["connection"]
    print(
        f"[{row['label']}] {row['environment_label']} session={conn['session_state']} "
        f"fidelity={conn['sandbox_fidelity']} base={row['base_currency']} "
        f"identity={row['external_identity']}"
    )
assert len({row["id"] for row in onboarded}) == 4
assert len({row["external_identity"] for row in onboarded}) == 4

grants = []
for row in onboarded:
    grant = client.post(
        "/api/account-grants",
        headers=headers,
        json={
            "account_id": row["id"],
            "assigned_principal_id": f"execsvc://worker-{row['label'].split()[-1].lower()}",
            "allowed_environments": [row["connection"]["environment"]],
            "egress_allowlist": ["mock.local"],
        },
    )
    assert grant.status_code == 201, grant.text
    grants.append(grant.json())

print("\n== grants: one execution identity per account secret ==")
for grant in grants:
    print(
        f"[{grant['assigned_principal_id']}] {grant['secret_ref']} "
        f"state={grant['state']} v{grant['secret_version']}"
    )

# Rotate one credential (Mock beta) and show the single-record invariant.
rotated = client.post(
    f"/api/account-grants/{grants[1]['id']}/rotate",
    headers=headers,
    json={"credentials": {
        "api_key": "ak-demo-ROTATED-KEY-002",
        "api_secret": "as-demo-ROTATED-SECRET-002",
        "token_expires_at": FRESH,
    }},
)
assert rotated.status_code == 200, rotated.text
body = rotated.json()
assert body["secret_version"] == 2 and body["state"] == "ROTATED"

# Rotating the SAME external account again must not mint a second record.
repeat_onboard = client.post(
    "/api/broker-accounts",
    headers=headers,
    json={
        "label": "Mock beta (again)",
        "provider": "mock",
        "environment": "synthetic-paper",
        "external_account_id": "ext-demo-002",
        "credentials": {"api_key": "ak-demo-SECRET-002", "api_secret": "as-demo-SECRET-002"},
    },
)
assert repeat_onboard.status_code == 409

print("\n== rotation: Mock beta rotated in place, duplicate external account rejected ==")
print(f"[rotate] version 1 -> {body['secret_version']}, state={body['state']}, same grant row")
print(f"[duplicate re-onboard] HTTP {repeat_onboard.status_code} "
      f"({repeat_onboard.json()['detail'][:58]}…)")

# A capability preview rejection (deployment never submits unsupported orders).
preview = client.post(
    "/api/broker-accounts/preview",
    headers=headers,
    json={"provider": "mock", "environment": "synthetic-paper",
          "product": "equity", "order_type": "stop"},
).json()
print(f"\n== preview: equity stop on mock venue -> {preview['decision']} "
      f"(unknown features are disabled)")

print("\n== per-account status ==")
status = client.get("/api/broker-accounts", headers=headers).json()
for row in status:
    conn = row["connection"]
    grant = [g for g in client.get("/api/account-grants", headers=headers).json()
             if g["account_id"] == row["id"]][0]
    print(
        f"[{row['label']}] status={row['status']} session={conn['session_state']} "
        f"secret={grant['state']} v{grant['secret_version']} "
        f"reconciliation={conn['reconciliation_state']}"
    )

# Recovery posture: revoke delta's grant and show needs-reconciliation (not flat).
delta_grant = grants[3]
revoked = client.post(
    f"/api/account-grants/{delta_grant['id']}/revoke", headers=headers
)
assert revoked.status_code == 200, revoked.text
final = client.get("/api/broker-accounts", headers=headers).json()
delta = [r for r in final if r["label"] == "Mock delta"][0]
assert delta["status"] == "frozen"
assert delta["connection"]["reconciliation_state"] == "needs_reconciliation"
print("\n== recovery: revoked Mock delta ==")
print(
    f"[Mock delta] status={delta['status']} session={delta['connection']['session_state']} "
    f"reconciliation={delta['connection']['reconciliation_state']} "
    f"({delta['connection']['reconciliation_reason']}) — exposure flagged, not flat"
)
print("\nA04 demo complete: 4 accounts onboarded, 1 rotated in place, 1 revoked+flagged.")
