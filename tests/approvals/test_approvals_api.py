"""Approval queue acceptance tests (AC 1, 2, 4): state machine, parking,
latency, expiry, broadcast states, tenancy.

State-machine proof matrix:
- legal: parked -> approved, parked -> rejected, parked -> expired (sweep)
- illegal (409): approved -> approved, approved -> rejected, rejected ->
  approved, expired -> approved
- reject without reason: 422
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select

from algobots.api.approvals.models import ActionLedger, ApprovalRequest
from algobots.api.approvals.service import decide_request, park_order
from algobots.api.database import get_session_factory
from algobots.api.models import Account, Order, User


def _make_account(client, headers, label="Semi", mode="semi_auto", broker="alpaca") -> dict:
    response = client.post(
        "/api/accounts",
        headers=headers,
        json={"label": label, "broker": broker, "mode": mode},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _park(client, headers, account_id, symbol="AAPL", qty=100.0, side="buy") -> tuple[dict, str]:
    response = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account_id, "symbol": symbol, "side": side, "qty": qty},
    )
    assert response.status_code == 201, response.text
    assert response.headers.get("X-Approval-Request-Id"), response.headers
    return response.json(), response.headers["X-Approval-Request-Id"]


def _get_request(client, headers, request_id) -> dict:
    response = client.get(f"/api/approvals/{request_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _decide(client, headers, request_id, verdict, reason=""):
    return client.post(
        f"/api/approvals/{request_id}/decide",
        headers=headers,
        json={"verdict": verdict, "reason": reason},
    )


def _ledger(client, headers) -> list[dict]:
    response = client.get("/api/approvals/ledger", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _force_expiry(request_id) -> None:
    """Push one request past its TTL via the ORM (bind-processor consistent)."""
    session = get_session_factory()()
    try:
        request = session.get(ApprovalRequest, UUID(str(request_id)))
        request.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()


# --- parking rule (paper-only standing law) ---------------------------------------


def test_semi_auto_order_parks_instead_of_pending(client, member_headers):
    account = _make_account(client, member_headers)
    order, request_id = _park(client, member_headers, account["id"], symbol="aapl")

    assert order["status"] == "parked"  # never dispatched, never pending
    body = _get_request(client, member_headers, request_id)
    assert body["status"] == "parked"
    assert "semi_auto" in body["park_reason"]
    assert body["symbol"] == "AAPL"
    assert body["qty"] == 100.0
    assert body["latency_ms"] is None  # no decision yet

    parked = client.get("/api/approvals", headers=member_headers, params={"status": "parked"})
    assert [r["id"] for r in parked.json()] == [request_id]

    entries = [row for row in _ledger(client, member_headers) if row["action"] == "order_parked"]
    assert len(entries) == 1
    assert "semi_auto" in entries[0]["reason"]
    assert entries[0]["latency_ms"] is None  # park action carries no duration


def test_paper_order_does_not_park(client, member_headers):
    account = _make_account(client, member_headers, label="Plain", mode="paper")
    response = client.post(
        "/api/orders",
        headers=member_headers,
        json={"account_id": account["id"], "symbol": "AAPL", "side": "buy", "qty": 10},
    )
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "pending"
    assert "X-Approval-Request-Id" not in response.headers
    empty = client.get("/api/approvals", headers=member_headers)
    assert empty.json() == []


# --- legal transitions -------------------------------------------------------------


def test_parked_to_approved_records_actor_reason_latency(client, member_headers, member):
    account = _make_account(client, member_headers)
    order, request_id = _park(client, member_headers, account["id"])

    verdict = _decide(client, member_headers, request_id, "approved", reason="within envelope")
    assert verdict.status_code == 200, verdict.text
    body = verdict.json()
    assert body["status"] == "approved"
    assert body["decision_reason"] == "within envelope"
    assert body["decided_by"] == member["user"]["id"]
    assert isinstance(body["latency_ms"], int) and body["latency_ms"] >= 0
    assert body["decided_at"] is not None

    # The parked order is released (paper-only dispatch, never a broker call).
    order_after = client.get(f"/api/orders/{order['id']}", headers=member_headers)
    assert order_after.json()["status"] == "submitted"

    ledger = _ledger(client, member_headers)
    approved_rows = [row for row in ledger if row["action"] == "approval_approved"]
    assert len(approved_rows) == 1
    assert approved_rows[0]["reason"] == "within envelope"
    assert approved_rows[0]["latency_ms"] == body["latency_ms"]  # persisted per action


def test_parked_to_rejected_requires_and_records_reason(client, member_headers):
    account = _make_account(client, member_headers)
    order, request_id = _park(client, member_headers, account["id"])

    missing = _decide(client, member_headers, request_id, "rejected", reason="")
    assert missing.status_code == 422
    assert "reason" in missing.json()["detail"].lower()

    verdict = _decide(client, member_headers, request_id, "rejected", reason="too large for size")
    assert verdict.status_code == 200, verdict.text
    body = verdict.json()
    assert body["status"] == "rejected"
    assert body["decision_reason"] == "too large for size"
    assert isinstance(body["latency_ms"], int)

    order_after = client.get(f"/api/orders/{order['id']}", headers=member_headers)
    assert order_after.json()["status"] == "cancelled"

    rows = [row for row in _ledger(client, member_headers) if row["action"] == "approval_rejected"]
    assert rows[0]["reason"] == "too large for size"
    assert rows[0]["latency_ms"] == body["latency_ms"]


def test_parked_to_expired_via_sweep(client, member_headers):
    account = _make_account(client, member_headers)
    order, request_id = _park(client, member_headers, account["id"])

    # Not yet due: the sweep is a no-op while TTL (default 300s) stands.
    early = client.post("/api/approvals/sweep-expiry", headers=member_headers)
    assert early.status_code == 200 and early.json() == {"expired": 0}

    _force_expiry(request_id)

    swept = client.post("/api/approvals/sweep-expiry", headers=member_headers)
    assert swept.status_code == 200 and swept.json() == {"expired": 1}

    body = _get_request(client, member_headers, request_id)
    assert body["status"] == "expired"
    assert isinstance(body["latency_ms"], int)  # park -> expiry latency persisted
    order_after = client.get(f"/api/orders/{order['id']}", headers=member_headers)
    assert order_after.json()["status"] == "cancelled"

    rows = [row for row in _ledger(client, member_headers) if row["action"] == "approval_expired"]
    assert len(rows) == 1 and rows[0]["latency_ms"] == body["latency_ms"]

    # Idempotent: already-expired requests are never re-transitioned.
    again = client.post("/api/approvals/sweep-expiry", headers=member_headers)
    assert again.json() == {"expired": 0}


# --- illegal transitions (409) ------------------------------------------------------


def test_illegal_transitions_rejected_409(client, member_headers):
    account = _make_account(client, member_headers)

    # approved is terminal
    _, approved_id = _park(client, member_headers, account["id"])
    assert _decide(client, member_headers, approved_id, "approved").status_code == 200
    for verdict in ("approved", "rejected"):
        repeat = _decide(client, member_headers, approved_id, verdict, reason="again")
        assert repeat.status_code == 409
        assert "Illegal approval transition" in repeat.json()["detail"]

    # rejected is terminal
    _, rejected_id = _park(client, member_headers, account["id"])
    assert _decide(client, member_headers, rejected_id, "rejected", reason="no").status_code == 200
    revive = _decide(client, member_headers, rejected_id, "approved")
    assert revive.status_code == 409

    # expired is terminal
    _, expired_id = _park(client, member_headers, account["id"])
    _force_expiry(expired_id)
    assert client.post("/api/approvals/sweep-expiry", headers=member_headers).json()["expired"] == 1
    zombie = _decide(client, member_headers, expired_id, "approved")
    assert zombie.status_code == 409


def test_decide_unknown_request_and_cross_tenant_404(client, member_headers, founder_headers):
    account = _make_account(client, member_headers)
    _, request_id = _park(client, member_headers, account["id"])

    missing = _decide(client, member_headers, str(uuid4()), "approved")
    assert missing.status_code == 404

    foreign = _decide(client, founder_headers, request_id, "approved")
    assert foreign.status_code == 404
    invisible = client.get(f"/api/approvals/{request_id}", headers=founder_headers)
    assert invisible.status_code == 404
    assert client.get("/api/approvals", headers=founder_headers).json() == []


# --- deterministic latency proof (service level) -----------------------------------


def test_latency_math_park_to_decision_deterministic(founder):
    session = get_session_factory()()
    try:
        user = session.scalar(select(User).where(User.email == founder["email"]))
        account = Account(
            user_id=user.id,
            label=f"semi-{user.id.hex[:6]}",
            broker="alpaca",
            mode="semi_auto",
            status="active",
            base_currency="USD",
        )
        session.add(account)
        session.flush()
        order = Order(
            user_id=user.id,
            account_id=account.id,
            symbol="AAPL",
            side="buy",
            order_type="market",
            qty=10.0,
            status="parked",
        )
        session.add(order)
        session.flush()

        parked_at = datetime.now(UTC) - timedelta(milliseconds=1500)
        request = park_order(session, order, parked_at=parked_at)
        decided = decide_request(
            session,
            user,
            request,
            "approved",
            "deterministic",
            decided_at=parked_at + timedelta(milliseconds=1500),
        )
        assert decided.latency_ms == 1500  # exact park -> decision measure
        rows = list(
            session.scalars(
                select(ActionLedger).where(ActionLedger.subject_id == request.id)
            )
        )
        approved_rows = [row for row in rows if row.action == "approval_approved"]
        assert approved_rows[0].latency_ms == 1500  # same measure in the ledger
    finally:
        session.rollback()
        session.close()


# --- broadcast states (AC 4) ---------------------------------------------------------


def _approved_request(client, headers, qty=100.0):
    account = _make_account(client, headers, label=f"bc-{uuid4().hex[:8]}")
    _, request_id = _park(client, headers, account["id"], qty=qty)
    verdict = _decide(client, headers, request_id, "approved", reason="go")
    assert verdict.status_code == 200, verdict.text
    return request_id


def _broadcast(client, headers, request_id, sent, queued, reason=""):
    return client.post(
        f"/api/approvals/{request_id}/broadcast",
        headers=headers,
        json={"sent_qty": sent, "queued_qty": queued, "reason": reason},
    )


def test_broadcast_partial_fill_states(client, member_headers):
    # Part executed, remainder queued -> part_queued
    mixed_id = _approved_request(client, member_headers)
    mixed = _broadcast(client, member_headers, mixed_id, 60.0, 40.0)
    assert mixed.status_code == 200, mixed.text
    assert mixed.json()["state"] == "part_queued"
    assert mixed.json()["total_qty"] == 100.0
    assert mixed.json()["latency_ms"] is not None  # decision -> report latency

    # Fully executed -> sent
    sent_id = _approved_request(client, member_headers)
    assert _broadcast(client, member_headers, sent_id, 100.0, 0.0).json()["state"] == "sent"

    # Partially executed, nothing queued -> part_sent
    partial_id = _approved_request(client, member_headers)
    outcome = _broadcast(client, member_headers, partial_id, 50.0, 0.0)
    assert outcome.json()["state"] == "part_sent"

    # Nothing executed, fully queued -> queued
    queued_id = _approved_request(client, member_headers)
    assert _broadcast(client, member_headers, queued_id, 0.0, 100.0).json()["state"] == "queued"

    # The broadcast lands on the approval read model and in the ledger.
    body = _get_request(client, member_headers, mixed_id)
    assert body["broadcast"]["state"] == "part_queued"
    rows = [row for row in _ledger(client, member_headers) if row["action"] == "broadcast_reported"]
    assert len(rows) == 4
    assert rows[0]["detail_json"]["state"] == "queued"  # newest first


def test_broadcast_validation(client, member_headers):
    # Not approved yet -> 409
    account = _make_account(client, member_headers)
    _, parked_id = _park(client, member_headers, account["id"])
    parked = _broadcast(client, member_headers, parked_id, 10.0, 0.0)
    assert parked.status_code == 409

    approved_id = _approved_request(client, member_headers)
    # Over-report -> 422
    over = _broadcast(client, member_headers, approved_id, 80.0, 80.0)
    assert over.status_code == 422
    # Both zero -> 422
    zero = _broadcast(client, member_headers, approved_id, 0.0, 0.0)
    assert zero.status_code == 422
    # Duplicate -> 409
    assert _broadcast(client, member_headers, approved_id, 100.0, 0.0).status_code == 200
    dup = _broadcast(client, member_headers, approved_id, 100.0, 0.0)
    assert dup.status_code == 409


def test_list_filter_by_order(client, member_headers):
    account = _make_account(client, member_headers)
    order_a, request_a = _park(client, member_headers, account["id"], symbol="MSFT")
    _park(client, member_headers, account["id"], symbol="AAPL")

    filtered = client.get(
        "/api/approvals", headers=member_headers, params={"order_id": order_a["id"]}
    )
    assert [r["id"] for r in filtered.json()] == [request_a]
    assert filtered.json()[0]["symbol"] == "MSFT"
