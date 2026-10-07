"""Action-ledger immutability + per-action evidence tests (AC 2, 3).

AC 3 proof: the append-only law is enforced AT THE DATABASE LEVEL by the
migration-0004 triggers — raw SQL UPDATE and raw SQL DELETE both fail, and
so does an ORM update. (Distinct from the S0.2 `audit_log` middleware
table, which is not trigger-protected.)
"""

import pytest
from sqlalchemy import select, text

from algobots.api.approvals.models import ActionLedger
from algobots.api.database import get_engine, get_session_factory
from algobots.api.models import User


def _make_account(client, headers, label="Ledger"):
    response = client.post(
        "/api/accounts",
        headers=headers,
        json={"label": label, "broker": "alpaca", "mode": "semi_auto"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _park(client, headers, account_id) -> str:
    response = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account_id, "symbol": "AAPL", "side": "buy", "qty": 10},
    )
    assert response.status_code == 201, response.text
    return response.headers["X-Approval-Request-Id"]


@pytest.fixture()
def ledger_seed(client, member_headers):
    """Park + approve one order so the ledger has rows to attack."""
    account = _make_account(client, member_headers)
    request_id = _park(client, member_headers, account["id"])
    verdict = client.post(
        f"/api/approvals/{request_id}/decide",
        headers=member_headers,
        json={"verdict": "approved", "reason": "ledger immutability seed"},
    )
    assert verdict.status_code == 200, verdict.text
    return member_headers


def _row_hex_id() -> str:
    """One ledger row id as stored (SQLite Uuid renders CHAR(32) hex, no hyphens)."""
    session = get_session_factory()()
    try:
        return session.scalar(select(ActionLedger.id).limit(1)).hex
    finally:
        session.close()


def test_raw_sql_update_fails(ledger_seed):
    with get_engine().begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.exec_driver_sql("UPDATE action_ledger SET reason = 'tampered'")


def test_raw_sql_delete_fails(ledger_seed):
    with get_engine().begin() as conn:
        with pytest.raises(Exception, match="append-only"):
            conn.exec_driver_sql(f"DELETE FROM action_ledger WHERE id = '{_row_hex_id()}'")


def test_orm_update_fails(ledger_seed):
    session = get_session_factory()()
    try:
        row = session.scalar(select(ActionLedger).limit(1))
        row.reason = "orm tamper"
        with pytest.raises(Exception, match="append-only"):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_orm_delete_fails(ledger_seed):
    session = get_session_factory()()
    try:
        row = session.scalar(select(ActionLedger).limit(1))
        session.delete(row)
        with pytest.raises(Exception, match="append-only"):
            session.commit()
    finally:
        session.rollback()
        session.close()


def test_ledger_distinct_from_audit_log_and_records_evidence(ledger_seed, member):
    """Ledger rows carry actor/reason/latency; the HTTP audit_log stays separate."""
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == member["email"]))
        # scoped to this tenant: other suites (e.g. the /demo registry) share the DB
        rows = list(
            session.scalars(
                select(ActionLedger)
                .where(ActionLedger.user_id == user.id)
                .order_by(ActionLedger.created_at)
            )
        )
        actions = [row.action for row in rows]
        assert actions[0] == "order_parked"
        assert actions[-1] == "approval_approved"
        approved = rows[-1]
        assert approved.actor_id == user.id
        assert approved.reason == "ledger immutability seed"
        assert approved.latency_ms is not None  # park -> decision latency per action
        assert rows[0].latency_ms is None  # the park action itself has no duration

        audit_rows = session.execute(text("SELECT COUNT(*) FROM audit_log")).scalar_one()
        assert audit_rows >= 1  # middleware table exists alongside, separate
    finally:
        session.close()
