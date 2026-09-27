"""S4.1 acceptance tests: account registry (ALG-3090).

Q&A gate coverage:
1. Multi-account-per-user-per-broker CRUD (paper/live per account).
2. Credentials encrypted at rest — plaintext provably absent from raw DB bytes.
3. Token-health sweep silently refreshes or marks expired; never crashes.
4. No secret ever appears in logs, audit rows, or API responses (assert-tested).
"""

import logging
import traceback
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from algobots.api.accounts.crypto import REDACTED, get_credential_cipher
from algobots.api.accounts.models import AccountCredential
from algobots.api.accounts.refresh import REFRESHERS, RefreshOutcome
from algobots.api.accounts.service import sweep_token_health
from algobots.api.database import get_session_factory
from algobots.api.models import Account
from algobots.dashboard.accounts import registry_snapshot, render_accounts_html

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
