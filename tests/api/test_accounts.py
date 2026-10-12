"""S4.1 acceptance tests: account registry (ALG-3090).

Q&A gate coverage:
1. Multi-account-per-user-per-broker CRUD (paper/live per account).
2. Credentials encrypted at rest — plaintext provably absent from raw DB bytes.
3. Token-health sweep silently refreshes or marks expired; never crashes.
4. No secret ever appears in logs, audit rows, or API responses (assert-tested).
"""

import json as _json
import logging
import traceback
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from algobots.api.accounts.crypto import REDACTED, get_credential_cipher
from algobots.api.accounts.models import AccountCredential, ExternalAccountIdentity
from algobots.api.accounts.refresh import REFRESHERS, RefreshOutcome
from algobots.api.accounts.service import sweep_token_health
from algobots.api.database import get_session_factory
from algobots.api.models import Account, AuditLog
from algobots.dashboard.accounts import registry_snapshot, render_accounts_html
from algobots.secrets import ResolutionDenied, SecretStore, build_secret_ref
from algobots.secrets.models import SecretGrant

SECRET_API_KEY = "ak-live-SECRET-7f3d2a"
SECRET_API_SECRET = "as-SECRET-9b2c41-DO-NOT-LOG"
SECRET_TOKEN = "tok-SECRET-4e19c8"
NEW_TOKEN = "tok-NEW-51d0aa"

EXPIRING = datetime.now(UTC) + timedelta(seconds=10)  # inside refresh margin
FRESH = datetime.now(UTC) + timedelta(hours=1)


def _make_account(client, headers, *, label="Main", broker="alpaca", mode="paper") -> dict:
    response = client.post(
        "/api/accounts",
        headers=headers,
        json={"label": label, "broker": broker, "mode": mode},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _put_credentials(client, headers, account_id, *, token=SECRET_TOKEN, token_expires_at=None):
    body = {"api_key": SECRET_API_KEY, "api_secret": SECRET_API_SECRET}
    if token is not None:
        body["token"] = token
        body["token_expires_at"] = (token_expires_at or EXPIRING).isoformat()
    response = client.put(f"/api/accounts/{account_id}/credentials", headers=headers, json=body)
    assert response.status_code == 200, response.text
    return response.json()


def _db_session():
    return get_session_factory()()


def _db_file_bytes() -> bytes:
    from tests.conftest import _DB_PATH

    return _DB_PATH.read_bytes()


# --- CRUD: multi-account-per-user-per-broker, paper/live per account ---


def test_multi_account_per_user_per_broker(client: TestClient, member_headers):
    paper = _make_account(client, member_headers, label="Play money", broker="alpaca")
    live = _make_account(client, member_headers, label="Real money", broker="alpaca", mode="live")
    assert paper["id"] != live["id"]
    assert paper["mode"] == "paper" and live["mode"] == "live"

    listed = client.get("/api/accounts", headers=member_headers).json()
    alpaca = [a for a in listed if a["broker"] == "alpaca"]
    assert len(alpaca) == 2
    assert {a["mode"] for a in alpaca} == {"paper", "live"}

    # PATCH flips mode per account without touching the sibling
    flipped = client.patch(
        f"/api/accounts/{paper['id']}", headers=member_headers, json={"mode": "live"}
    )
    assert flipped.status_code == 200 and flipped.json()["mode"] == "live"
    sibling = client.get(f"/api/accounts/{live['id']}", headers=member_headers).json()
    assert sibling["mode"] == "live" and sibling["label"] == "Real money"


def test_duplicate_label_per_user_rejected(client: TestClient, member_headers):
    _make_account(client, member_headers, label="Same", broker="alpaca")
    dup = client.post(
        "/api/accounts", headers=member_headers, json={"label": "Same", "broker": "ibkr"}
    )
    assert dup.status_code == 409


def test_registry_crud_lifecycle(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Lifecycle", broker="ibkr")
    got = client.get(f"/api/accounts/{account['id']}", headers=member_headers)
    assert got.status_code == 200 and got.json()["label"] == "Lifecycle"

    deleted = client.delete(f"/api/accounts/{account['id']}", headers=member_headers)
    assert deleted.status_code == 204
    gone = client.get(f"/api/accounts/{account['id']}", headers=member_headers)
    assert gone.status_code == 404


def test_tenant_isolation_on_credentials(client: TestClient, member_headers, founder_headers):
    account = _make_account(client, member_headers, label="Mine", broker="alpaca")
    _put_credentials(client, member_headers, account["id"])
    for method, path in [
        ("PUT", f"/api/accounts/{account['id']}/credentials"),
        ("GET", f"/api/accounts/{account['id']}/credentials/health"),
        ("DELETE", f"/api/accounts/{account['id']}/credentials"),
    ]:
        response = client.request(
            method,
            path,
            headers=founder_headers,
            json={
                "api_key": "x-key-tenant-b",
                "api_secret": "x-secret-tenant-b",
                "token": "x-token-tenant-b",
            },
        )
        assert response.status_code == 404, (method, response.text)


def test_delete_account_forgets_credentials(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Bye", broker="alpaca")
    _put_credentials(client, member_headers, account["id"])
    deleted = client.delete(f"/api/accounts/{account['id']}", headers=member_headers)
    assert deleted.status_code == 204
    with _db_session() as db:
        rows = db.query(AccountCredential).filter_by(account_id=UUID(account["id"])).all()
        assert rows == []


# --- encryption at rest ---


def test_credentials_encrypted_at_rest(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Vault", broker="alpaca")
    _put_credentials(client, member_headers, account["id"])

    with _db_session() as db:
        row = db.query(AccountCredential).filter_by(account_id=UUID(account["id"])).one()
        assert row.encrypted_secrets.startswith("gAAA")  # Fernet token, not plaintext
        assert SECRET_API_KEY not in row.encrypted_secrets
        assert SECRET_API_SECRET not in row.encrypted_secrets
        decrypted = get_credential_cipher().decrypt(row.encrypted_secrets)
        assert decrypted["api_key"] == SECRET_API_KEY
        assert decrypted["api_secret"] == SECRET_API_SECRET
        assert row.token_status == "active"

    # Strongest at-rest proof: plaintext bytes nowhere in the whole DB file.
    db_bytes = _db_file_bytes()
    for secret in (SECRET_API_KEY, SECRET_API_SECRET, SECRET_TOKEN):
        assert secret.encode() not in db_bytes, f"plaintext secret leaked into DB: {secret}"


def test_credentials_absent_from_every_response(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Opaque", broker="alpaca")
    put = client.put(
        f"/api/accounts/{account['id']}/credentials",
        headers=member_headers,
        json={
            "api_key": SECRET_API_KEY,
            "api_secret": SECRET_API_SECRET,
            "token": SECRET_TOKEN,
            "token_expires_at": EXPIRING.isoformat(),
        },
    )
    health = client.get(f"/api/accounts/{account['id']}/credentials/health", headers=member_headers)
    got = client.get(f"/api/accounts/{account['id']}", headers=member_headers)
    sweep = client.post("/api/accounts/token-sweep", headers=member_headers)
    for response in (put, health, got, sweep):
        assert response.status_code == 200, response.text
        for secret in (SECRET_API_KEY, SECRET_API_SECRET, SECRET_TOKEN):
            assert secret not in response.text


# --- token-health sweep: silent-refresh-or-expire, never crashes ---


class FakeRefresher:
    """Records calls; optionally raises an error echoing the secret token."""

    def __init__(self, *, fail_with: Exception | None = None):
        self.calls: list[tuple[str, dict]] = []
        self.fail_with = fail_with

    def __call__(self, account, secrets):
        self.calls.append((account.broker, dict(secrets)))
        if self.fail_with:
            raise self.fail_with
        return RefreshOutcome(token=NEW_TOKEN, token_expires_at=FRESH)


@pytest.fixture()
def alpaca_refresher():
    refresher = FakeRefresher()
    REFRESHERS["alpaca"] = refresher
    yield refresher
    REFRESHERS.pop("alpaca", None)


def test_sweep_silently_refreshes_expiring_token(
    client: TestClient, member_headers, alpaca_refresher: FakeRefresher
):
    account = _make_account(client, member_headers, label="Refresh me", broker="alpaca")
    _put_credentials(client, member_headers, account["id"])  # expires inside margin

    report = client.post("/api/accounts/token-sweep", headers=member_headers).json()
    assert report["checked"] == 1 and report["refreshed"] == 1 and report["expired"] == 0
    assert report["expired_account_ids"] == []

    broker, secrets = alpaca_refresher.calls[0]
    assert broker == "alpaca" and secrets["api_key"] == SECRET_API_KEY

    with _db_session() as db:
        row = db.query(AccountCredential).filter_by(account_id=UUID(account["id"])).one()
        assert row.token_status == "active"
        assert row.last_refreshed_at is not None and row.last_refresh_error == ""
        resealed = get_credential_cipher().decrypt(row.encrypted_secrets)
        assert resealed["token"] == NEW_TOKEN
        assert SECRET_TOKEN not in row.encrypted_secrets

    health = client.get(
        f"/api/accounts/{account['id']}/credentials/health", headers=member_headers
    ).json()
    assert health["token_status"] == "active" and health["last_refreshed_at"] is not None


def test_sweep_leaves_healthy_tokens_alone(client: TestClient, member_headers, alpaca_refresher):
    account = _make_account(client, member_headers, label="Still fine", broker="alpaca")
    _put_credentials(client, member_headers, account["id"], token_expires_at=FRESH)
    report = client.post("/api/accounts/token-sweep", headers=member_headers).json()
    assert report["checked"] == 1 and report["healthy"] == 1
    assert report["refreshed"] == 0 and report["expired"] == 0 and report["failed"] == 0
    assert report["expired_account_ids"] == []
    assert alpaca_refresher.calls == []


def test_sweep_marks_expired_when_no_refresher(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Orphan broker", broker="zen-broker")
    _put_credentials(client, member_headers, account["id"])
    report = client.post("/api/accounts/token-sweep", headers=member_headers).json()
    assert report["checked"] == 1 and report["expired"] == 1
    assert report["expired_account_ids"] == [account["id"]]

    health = client.get(
        f"/api/accounts/{account['id']}/credentials/health", headers=member_headers
    ).json()
    assert health["token_status"] == "expired"
    assert "no token refresher" in health["last_refresh_error"]
    # The account itself is untouched — expiry pauses trading, not the registry.
    got = client.get(f"/api/accounts/{account['id']}", headers=member_headers)
    assert got.status_code == 200 and got.json()["status"] == "active"


def test_sweep_survives_refresher_crash_and_redacts_secret(client: TestClient, member_headers):
    boom = FakeRefresher(
        fail_with=RuntimeError(f"broker 500 while refreshing token {SECRET_TOKEN}")
    )
    REFRESHERS["alpaca"] = boom
    try:
        account = _make_account(client, member_headers, label="Broken broker", broker="alpaca")
        _put_credentials(client, member_headers, account["id"])
        report = client.post("/api/accounts/token-sweep", headers=member_headers).json()
        assert report["failed"] == 1 and report["checked"] == 1

        health = client.get(
            f"/api/accounts/{account['id']}/credentials/health", headers=member_headers
        ).json()
        assert health["token_status"] == "expired"
        assert SECRET_TOKEN not in health["last_refresh_error"]
        assert REDACTED in health["last_refresh_error"]
    finally:
        REFRESHERS.pop("alpaca", None)


def test_sweep_survives_undecryptable_blob(client: TestClient, member_headers):
    account = _make_account(client, member_headers, label="Corrupt blob", broker="alpaca")
    _put_credentials(client, member_headers, account["id"])
    with _db_session() as db:
        row = db.query(AccountCredential).filter_by(account_id=UUID(account["id"])).one()
        row.encrypted_secrets = "gAAAnot-a-real-fernet-token=="
        db.commit()
        owner_id = db.get(Account, UUID(account["id"])).user_id

    # A registered refresher forces the decrypt path; the corrupt blob is
    # marked expired, and no exception escapes the service call.
    REFRESHERS["alpaca"] = FakeRefresher()
    try:
        report = sweep_token_health(get_session_factory()(), user_id=owner_id)
    finally:
        REFRESHERS.pop("alpaca", None)
    assert report.checked == 1 and report.expired == 1
    assert report.expired_account_ids == [UUID(account["id"])]
    with _db_session() as db:
        row = db.query(AccountCredential).filter_by(account_id=UUID(account["id"])).one()
        assert row.token_status == "expired"
        assert "decryption failed" in row.last_refresh_error


def test_sweep_is_tenant_scoped(
    client: TestClient, member_headers, founder_headers, alpaca_refresher
):
    mine = _make_account(client, member_headers, label="Mine only", broker="alpaca")
    _put_credentials(client, member_headers, mine["id"])
    founder_report = client.post("/api/accounts/token-sweep", headers=founder_headers).json()
    assert founder_report["checked"] == 0
    my_report = client.post("/api/accounts/token-sweep", headers=member_headers).json()
    assert my_report["checked"] == 1


# --- no secret ever in logs (assert-tested) ---


def test_no_secrets_in_logs_or_audit(client: TestClient, member_headers, caplog):
    caplog.set_level(logging.DEBUG, logger="algobots")
    crashing = FakeRefresher(fail_with=RuntimeError(f"refresh blew up on {SECRET_TOKEN}"))
    REFRESHERS["alpaca"] = crashing
    try:
        ok = _make_account(client, member_headers, label="Logs A", broker="alpaca")
        orphan = _make_account(client, member_headers, label="Logs B", broker="zen-broker")
        _put_credentials(client, member_headers, ok["id"])
        _put_credentials(client, member_headers, orphan["id"])
        client.get(f"/api/accounts/{ok['id']}/credentials/health", headers=member_headers)
        sweep = client.post("/api/accounts/token-sweep", headers=member_headers)
        assert sweep.status_code == 200 and sweep.json()["checked"] == 2
    finally:
        REFRESHERS.pop("alpaca", None)

    for record in caplog.records:
        rendered = record.getMessage()
        for secret in (SECRET_API_KEY, SECRET_API_SECRET, SECRET_TOKEN):
            assert secret not in rendered, f"secret leaked to logger {record.name}: {rendered}"
        if record.exc_info:
            assert SECRET_TOKEN not in "".join(traceback.format_exception(*record.exc_info))

    with _db_session() as db:
        audit_rows = db.execute(
            text("SELECT method, path, status_code, resource, detail_json FROM audit_log")
        ).all()
        assert audit_rows, "audit middleware produced no rows"
        for row in audit_rows:
            blob = repr(row)
            for secret in (SECRET_API_KEY, SECRET_API_SECRET, SECRET_TOKEN):
                assert secret not in blob


# --- dashboard views ---


def test_dashboard_snapshot_groups_by_broker(client: TestClient, member_headers):
    a1 = _make_account(client, member_headers, label="Dash 1", broker="alpaca")
    _make_account(client, member_headers, label="Dash 2", broker="alpaca", mode="live")
    a3 = _make_account(client, member_headers, label="Dash 3", broker="ibkr")
    _put_credentials(client, member_headers, a3["id"], token_expires_at=FRESH)

    with _db_session() as db:
        row = db.query(AccountCredential).filter_by(account_id=UUID(a3["id"])).one()
        row.token_status = "expired"
        db.commit()

        user_id = db.get(Account, UUID(a1["id"])).user_id
        snapshot = registry_snapshot(db, user_id)

    assert set(snapshot["brokers"]) == {"alpaca", "ibkr"}
    assert {e["label"] for e in snapshot["brokers"]["alpaca"]} == {"Dash 1", "Dash 2"}
    assert snapshot["totals"] == {"accounts": 3, "paper": 2, "live": 1, "expired_tokens": 1}
    assert snapshot["brokers"]["ibkr"][0]["token_status"] == "expired"


def test_dashboard_html_renders(client: TestClient, member_headers):
    _make_account(client, member_headers, label="Render <me> & co", broker="alpaca")
    _make_account(client, member_headers, label="Second", broker="alpaca", mode="live")
    with _db_session() as db:
        user_id = db.query(Account).filter_by(label="Second").one().user_id
        snapshot = registry_snapshot(db, user_id)
    html_out = render_accounts_html(snapshot)
    assert "alpaca (2)" in html_out
    assert "Render &lt;me&gt; &amp; co" in html_out
    assert "Second" in html_out and "2 accounts" in html_out


# --- A04: onboarding, capability registry, secret grants (ALG-3100) ---


def row_detail(row) -> str:
    return row.detail_json or ""

A04_KEY = "ak-a04-SECRET-2f81c9"
A04_SECRET = "as-a04-SECRET-77b0de"
A04_TOKEN = "tok-a04-SECRET-31cc02"
A04_ROTATED_KEY = "ak-a04-ROTATED-KEY-90a1"
A04_ROTATED_SECRET = "as-a04-ROTATED-SECRET-4b2c"

PRINCIPAL_A = "execsvc://worker-alpha"


def _onboard(client, headers, *, label, external_id, provider="mock", environment="synthetic-paper",
             api_key=A04_KEY, api_secret=A04_SECRET, mode="paper", base_currency="USD"):
    response = client.post(
        "/api/broker-accounts",
        headers=headers,
        json={
            "label": label,
            "provider": provider,
            "environment": environment,
            "external_account_id": external_id,
            "base_currency": base_currency,
            "mode": mode,
            "credentials": {
                "api_key": api_key,
                "api_secret": api_secret,
                "token": A04_TOKEN,
                "token_expires_at": FRESH.isoformat(),
            },
        },
    )
    return response


def _grant(client, headers, account_id, *, principal=PRINCIPAL_A,
           environments=("synthetic-paper", "development"), hosts=("mock.local",)):
    return client.post(
        "/api/account-grants",
        headers=headers,
        json={
            "account_id": str(account_id),
            "assigned_principal_id": principal,
            "allowed_environments": list(environments),
            "egress_allowlist": list(hosts),
            "rotation_policy": "manual",
        },
    )


def test_a04_two_accounts_same_venue_are_fully_distinct(client: TestClient, member_headers):
    """AC1: same venue, two onboardings -> distinct identities, credentials,
    grants and environment labels."""
    first = _onboard(client, member_headers, label="Mock one", external_id="ext-mock-001",
                     environment="synthetic-paper").json()
    second = _onboard(client, member_headers, label="Mock two", external_id="ext-mock-002",
                      environment="development").json()

    assert first["id"] != second["id"]
    assert first["external_identity"] != second["external_identity"]
    assert first["environment_label"] == "mock:synthetic-paper"
    assert second["environment_label"] == "mock:development"
    assert first["connection"]["session_state"] == "CONNECTED"

    g1 = _grant(client, member_headers, first["id"], principal="execsvc://worker-one").json()
    g2 = _grant(client, member_headers, second["id"], principal="execsvc://worker-two").json()
    assert g1["secret_ref"] != g2["secret_ref"]
    assert g1["assigned_principal_id"] != g2["assigned_principal_id"]

    with _db_session() as db:
        ids = [UUID(first["id"]), UUID(second["id"])]
        assert db.query(AccountCredential).filter(
            AccountCredential.account_id.in_(ids)
        ).count() == 2
        fingerprints = {
            row.fingerprint for row in db.query(ExternalAccountIdentity).filter(
                ExternalAccountIdentity.account_id.in_(ids)
            )
        }
    assert len(fingerprints) == 2


def test_a04_no_plaintext_credential_anywhere(client: TestClient, member_headers, caplog):
    """AC2: no plaintext credential in API responses, DB bytes, logs or errors."""
    import logging as _logging

    with caplog.at_level(_logging.DEBUG, logger="algobots"):
        created = _onboard(client, member_headers, label="Leak probe", external_id="ext-mock-leak")
        assert created.status_code == 201, created.text
        account_id = created.json()["id"]
        grant = _grant(client, member_headers, account_id)
        assert grant.status_code == 201, grant.text
        dup = _onboard(client, member_headers, label="Leak probe 2", external_id="ext-mock-leak")
        assert dup.status_code == 409
        rotated = client.post(
            f"/api/account-grants/{grant.json()['id']}/rotate",
            headers=member_headers,
            json={"credentials": {
                "api_key": A04_ROTATED_KEY,
                "api_secret": A04_ROTATED_SECRET,
                "token": A04_TOKEN,
                "token_expires_at": FRESH.isoformat(),
            }},
        )
        assert rotated.status_code == 200, rotated.text

    blobs = [
        created.text, grant.text, dup.text, rotated.text,
        _json.dumps(_db_file_bytes()[:].decode("latin-1")),
        caplog.text,
    ]
    for secret in (A04_KEY, A04_SECRET, A04_TOKEN, A04_ROTATED_KEY, A04_ROTATED_SECRET):
        for blob in blobs:
            assert secret not in blob, f"plaintext {secret[:8]}… leaked"


def test_a04_cross_tenant_and_cross_principal_resolution_denied(
    client: TestClient, member_headers, founder_headers
):
    """AC3: tenant A worker credentials cannot resolve tenant B's secret; only
    the assigned execution identity in the owning tenant can."""
    created = _onboard(client, member_headers, label="AC3 target", external_id="ext-mock-ac3")
    account_id = created.json()["id"]
    grant = _grant(client, member_headers, account_id).json()

    with _db_session() as db:
        account = db.get(Account, UUID(account_id))
        owner_tenant = account.tenant_id

        store = SecretStore()
        # Allowed: the assigned execution identity inside the owning tenant.
        resolution = store.resolve(
            db,
            principal_id=PRINCIPAL_A,
            principal_tenant_id=owner_tenant,
            secret_ref=grant["secret_ref"],
            environment="synthetic-paper",
        )
        assert resolution.secrets["api_key"] == A04_KEY
        assert resolution.egress_allowlist == ("mock.local",)

        # Tenant A worker asking for tenant B's secret: denied (tenant mismatch).
        foreign_tenant = UUID("00000000-0000-0000-0000-000000000001")
        with pytest.raises(ResolutionDenied, match="cross-tenant"):
            store.resolve(
                db,
                principal_id=PRINCIPAL_A,
                principal_tenant_id=foreign_tenant,
                secret_ref=grant["secret_ref"],
                environment="synthetic-paper",
            )

        # Same denial for a well-formed but nonexistent reference: a caller
        # outside the tenant cannot distinguish existing from absent grants
        # (no grant-existence oracle for guessed (tenant, account) pairs).
        ghost_ref = build_secret_ref(owner_tenant, UUID(int=0xABCDEF))
        with pytest.raises(ResolutionDenied, match="cross-tenant"):
            store.resolve(
                db,
                principal_id=PRINCIPAL_A,
                principal_tenant_id=foreign_tenant,
                secret_ref=ghost_ref,
                environment="synthetic-paper",
            )

        # Right tenant, wrong execution identity: denied.
        with pytest.raises(ResolutionDenied, match="assigned execution identity"):
            store.resolve(
                db,
                principal_id="execsvc://worker-other",
                principal_tenant_id=owner_tenant,
                secret_ref=grant["secret_ref"],
                environment="synthetic-paper",
            )

        # Wrong environment: denied.
        with pytest.raises(ResolutionDenied, match="not allowed"):
            store.resolve(
                db,
                principal_id=PRINCIPAL_A,
                principal_tenant_id=owner_tenant,
                secret_ref=grant["secret_ref"],
                environment="paper",
            )

        # Non-allowlisted egress destination: denied.
        with pytest.raises(ResolutionDenied, match="allowlisted"):
            store.resolve(
                db,
                principal_id=PRINCIPAL_A,
                principal_tenant_id=owner_tenant,
                secret_ref=grant["secret_ref"],
                environment="synthetic-paper",
                egress_host="evil.example",
            )

        # Denials audited, with ids/reasons only — and cross-tenant probes are
        # attributed to the CALLER's tenant, not the victim's.
        denials = db.query(AuditLog).filter(AuditLog.path == "secret.resolution_denied").all()
        assert len(denials) == 5
        for row in denials:
            assert A04_KEY not in row.detail_json and A04_SECRET not in row.detail_json
        cross_tenant = [r for r in denials if "cross-tenant" in row_detail(r)]
        assert len(cross_tenant) == 2
        assert all(r.tenant_id == foreign_tenant for r in cross_tenant)


def test_a04_preview_rejects_unsupported_before_submission(client: TestClient, member_headers):
    """AC4: unsupported order types/products are rejected at preview time."""
    def preview(product, order_type, provider="mock", environment="synthetic-paper"):
        return client.post(
            "/api/broker-accounts/preview",
            headers=member_headers,
            json={"provider": provider, "environment": environment,
                  "product": product, "order_type": order_type},
        )

    allowed = preview("equity", "limit")
    assert allowed.status_code == 200 and allowed.json()["decision"] == "allowed"

    # stop orders are not in the mock catalog -> rejected pre-submission
    stopped = preview("equity", "stop")
    assert stopped.status_code == 200 and stopped.json()["decision"] == "rejected"
    assert "disabled" in stopped.json()["reason"]

    # spot-crypto is not offered by the mock venue at all
    crypto = preview("spot-crypto", "market")
    assert crypto.status_code == 200 and crypto.json()["decision"] == "rejected"

    # unknown provider -> no capability statement, rejected with 422
    unknown = preview("equity", "market", provider="notabroker")
    assert unknown.status_code == 422

    statement = client.get(
        "/api/broker-accounts/capabilities",
        headers=member_headers,
        params={"provider": "mock", "environment": "synthetic-paper"},
    )
    assert statement.status_code == 200
    entries = {(e["product"], e["order_type"]) for e in statement.json()["entries"]}
    assert ("equity", "stop") not in entries  # absent => disabled


def test_a04_rotation_keeps_single_ownership_record(client: TestClient, member_headers):
    """AC5: rotating credentials for the same external account creates no
    second account, identity or grant row."""
    created = _onboard(client, member_headers, label="Rotate me", external_id="ext-mock-rot")
    account_id = created.json()["id"]
    grant = _grant(client, member_headers, account_id).json()
    rotated = client.post(
        f"/api/account-grants/{grant['id']}/rotate",
        headers=member_headers,
        json={"credentials": {
            "api_key": A04_ROTATED_KEY,
            "api_secret": A04_ROTATED_SECRET,
            "token_expires_at": FRESH.isoformat(),
        }},
    )
    assert rotated.status_code == 200, rotated.text
    body = rotated.json()
    assert body["id"] == grant["id"]          # same grant row
    assert body["secret_version"] == 2        # version bumped in place
    assert body["state"] == "ROTATED"

    with _db_session() as db:
        account_uuid = UUID(account_id)
        accounts = db.query(Account).filter(Account.label == "Rotate me").all()
        assert len(accounts) == 1
        identities = db.query(ExternalAccountIdentity).filter(
            ExternalAccountIdentity.account_id == account_uuid
        ).all()
        assert len(identities) == 1 and identities[0].ownership_epoch == 1
        grants = db.query(SecretGrant).filter(SecretGrant.account_id == account_uuid).all()
        assert len(grants) == 1

        # The rotated secret resolves under the same grant reference.
        resolution = SecretStore().resolve(
            db,
            principal_id=PRINCIPAL_A,
            principal_tenant_id=accounts[0].tenant_id,
            secret_ref=grants[0].secret_ref,
            environment="synthetic-paper",
        )
        assert resolution.secrets["api_key"] == A04_ROTATED_KEY
        assert resolution.secret_version == 2


def test_a04_duplicate_external_account_conflict_hides_owner(
    client: TestClient, member_headers, founder_headers
):
    """Duplicate detection across tenants: 409 with no owner information."""
    first = _onboard(client, member_headers, label="Mine first", external_id="ext-mock-dup")
    assert first.status_code == 201
    owner = first.json()

    # A different tenant onboards the SAME external account.
    duplicate = _onboard(client, founder_headers, label="Second claim", external_id="ext-mock-dup")
    assert duplicate.status_code == 409
    body = duplicate.json()
    text = _json.dumps(body)
    # No tenant, account, user or label of the existing holder leaks.
    assert str(owner["tenant_id"]) not in text
    assert owner["id"] not in text
    assert "Mine first" not in text
    assert "already connected" in body["detail"]

    # Same tenant retrying also conflicts, still without owner data.
    again = _onboard(client, member_headers, label="Mine again", external_id="ext-mock-dup")
    assert again.status_code == 409


def test_a04_revoke_freezes_and_requires_reconciliation(client: TestClient, member_headers):
    """Recovery: revoked credentials freeze entries; exposure flags
    reconciliation instead of looking flat."""
    created = _onboard(client, member_headers, label="Revoke me", external_id="ext-mock-rev")
    account_id = created.json()["id"]
    grant = _grant(client, member_headers, account_id).json()

    revoked = client.post(
        f"/api/account-grants/{grant['id']}/revoke", headers=member_headers
    )
    assert revoked.status_code == 200, revoked.text
    body = revoked.json()
    assert body["state"] == "REVOKED" and body["revoked_at"] is not None

    listed = client.get("/api/broker-accounts", headers=member_headers).json()
    row = [r for r in listed if r["id"] == account_id][0]
    assert row["status"] == "frozen"
    assert row["connection"]["session_state"] == "EXPIRED"
    assert row["connection"]["reconciliation_state"] == "needs_reconciliation"
    assert row["connection"]["reconciliation_reason"] == "credentials revoked"

    with _db_session() as db:
        account = db.get(Account, UUID(account_id))
        with pytest.raises(ResolutionDenied, match="not resolvable"):
            SecretStore().resolve(
                db,
                principal_id=PRINCIPAL_A,
                principal_tenant_id=account.tenant_id,
                secret_ref=body["secret_ref"],
                environment="synthetic-paper",
            )

    # A revoked grant cannot rotate back to life.
    rotate = client.post(
        f"/api/account-grants/{grant['id']}/rotate",
        headers=member_headers,
        json={"credentials": {
            "api_key": A04_ROTATED_KEY, "api_secret": A04_ROTATED_SECRET,
        }},
    )
    assert rotate.status_code == 409


def test_a04_candidate_provider_is_configuration_only(client: TestClient, member_headers):
    """Mock onboards connected; the real provider candidate stays UNCONFIGURED
    and `live` is never onboardable."""
    candidate = _onboard(client, member_headers, label="Alpaca candidate",
                         external_id="ext-alpaca-9", provider="alpaca", environment="paper")
    assert candidate.status_code == 201, candidate.text
    assert candidate.json()["connection"]["session_state"] == "UNCONFIGURED"
    assert candidate.json()["connection"]["sandbox_fidelity"] == "partial"

    wrong_env = _onboard(client, member_headers, label="Alpaca dev",
                         external_id="ext-alpaca-10", provider="alpaca",
                         environment="development")
    assert wrong_env.status_code == 422

    live = _onboard(client, member_headers, label="Never live",
                    external_id="ext-mock-live", environment="live")
    assert live.status_code == 422

    unknown = _onboard(client, member_headers, label="Ghost",
                       external_id="ext-ghost", provider="notabroker")
    assert unknown.status_code == 422


def test_a04_registry_rows_are_tenant_scoped(client: TestClient, member_headers, founder_headers):
    """Broker-accounts and grant views never cross tenants."""
    mine = _onboard(client, member_headers, label="Only mine", external_id="ext-mock-iso")
    assert mine.status_code == 201
    account_id = mine.json()["id"]
    assert _grant(client, member_headers, account_id).status_code == 201

    their_accounts = client.get("/api/broker-accounts", headers=founder_headers).json()
    assert all(row["id"] != account_id for row in their_accounts)
    their_grants = client.get("/api/account-grants", headers=founder_headers).json()
    assert all(g["account_id"] != account_id for g in their_grants)

    stranger_grant = _grant(client, founder_headers, account_id,
                            principal="execsvc://founder-worker")
    assert stranger_grant.status_code == 404
