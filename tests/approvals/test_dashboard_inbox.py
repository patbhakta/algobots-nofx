"""Dashboard approval-inbox tests (AC 5): parked queue with reason/latency."""

from sqlalchemy import select

from algobots.api.database import get_session_factory
from algobots.api.models import User
from algobots.dashboard.approvals import approval_inbox_snapshot, render_approvals_html


def _make_account(client, headers, label="Inbox"):
    response = client.post(
        "/api/accounts", headers=headers, json={"label": label, "broker": "alpaca",
                                                "mode": "semi_auto"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _park(client, headers, account_id, symbol="AAPL") -> str:
    response = client.post(
        "/api/orders",
        headers=headers,
        json={"account_id": account_id, "symbol": symbol, "side": "buy", "qty": 25},
    )
    assert response.status_code == 201, response.text
    return response.headers["X-Approval-Request-Id"]


def _decide(client, headers, request_id, verdict, reason):
    response = client.post(
        f"/api/approvals/{request_id}/decide",
        headers=headers,
        json={"verdict": verdict, "reason": reason},
    )
    assert response.status_code == 200, response.text


def _user_id(email: str):
    session = get_session_factory()()
    try:
        return session.scalar(select(User).where(User.email == email)).id
    finally:
        session.close()


def test_inbox_lists_parked_with_reason_and_latency(client, member_headers, member):
    account = _make_account(client, member_headers)
    approve_id = _park(client, member_headers, account["id"], symbol="MSFT")
    reject_id = _park(client, member_headers, account["id"], symbol="TSLA")
    parked_id = _park(client, member_headers, account["id"], symbol="AAPL")
    _decide(client, member_headers, approve_id, "approved", "size ok")
    _decide(client, member_headers, reject_id, "rejected", "news risk")

    snapshot = approval_inbox_snapshot(get_session_factory()(), _user_id(member["email"]))

    assert snapshot["totals"] == {
        "requests": 3,
        "parked": 1,
        "approved": 1,
        "rejected": 1,
        "expired": 0,
    }
    (parked_entry,) = snapshot["parked"]
    assert parked_entry["id"] == parked_id
    assert "semi_auto" in parked_entry["park_reason"]  # reason shown while parked
    assert parked_entry["age_ms"] >= 0  # live wait (latency so far)
    assert parked_entry["latency_ms"] is None  # no verdict yet
    assert parked_entry["account_label"] == "Inbox"
    assert parked_entry["order_status"] == "parked"

    by_symbol = {entry["symbol"]: entry for entry in snapshot["decided"]}
    assert by_symbol["MSFT"]["decision_reason"] == "size ok"
    assert isinstance(by_symbol["MSFT"]["latency_ms"], int)  # persisted latency shown
    assert by_symbol["TSLA"]["decision_reason"] == "news risk"
    assert isinstance(by_symbol["TSLA"]["latency_ms"], int)

    actions = [row["action"] for row in snapshot["ledger"]]
    assert "order_parked" in actions and "approval_approved" in actions


def test_render_inbox_html_contains_reason_and_latency(client, member_headers, member):
    account = _make_account(client, member_headers, label="RenderAcct")
    approve_id = _park(client, member_headers, account["id"], symbol="MSFT")
    _park(client, member_headers, account["id"], symbol="AAPL")
    _decide(client, member_headers, approve_id, "approved", "rendered reason")

    snapshot = approval_inbox_snapshot(get_session_factory()(), _user_id(member["email"]))
    rendered = render_approvals_html(snapshot)

    assert "<section class='approvals-inbox'>" in rendered
    assert "Approval Inbox" in rendered
    assert "1 parked" in rendered and "1 approved" in rendered
    assert "rendered reason" in rendered  # decision reason
    assert "semi_auto" in rendered  # park reason
    assert "ms" in rendered  # latency display
    assert "order_parked" in rendered and "approval_approved" in rendered  # ledger rows
    assert "RenderAcct" in rendered
