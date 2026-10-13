"""A08 endpoints: /accounts/{id}/controls and /risk/preview (execution-contract)."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _policy_body() -> dict:
    return {
        "schema_version": "1.0",
        "policy_revision": "risk-a08-r1",
        "account_id": "acct-api",
        "base_currency": "USD",
        "timezone": "UTC",
        "permissions": [],
        "deployment_budgets": [],
        "constraints": {
            "fee_buffer_bps": "10",
            "slippage_buffer_bps": "5",
            "max_order_notional": {"amount": "500.00", "currency": "USD"},
        },
        "stale_state": {
            "max_mark_age_seconds": 30,
            "accepted_mark_qualities": ["REALTIME", "DELAYED"],
            "require_connected": True,
        },
        "created_at": "2026-10-07T12:00:00+00:00",
    }


def _preview_body(**state_overrides) -> dict:
    state = {
        "cash_available": "1000",
        "equity_reference": "1000",
        "connected": True,
        "instrument_mark": {
            "instrument_id": "KXA8.DEMO",
            "price": "100",
            "quality": "REALTIME",
            "observed_at": "2026-10-07T12:00:00+00:00",
        },
    }
    state.update(state_overrides)
    body = {
        "policy": _policy_body(),
        "proposal": {
            "account_id": "acct-api",
            "deployment_id": "dep-1",
            "instrument_id": "KXA8.DEMO",
            "side": "BUY",
            "kind": "ENTRY",
            "quantity": "5",
            "reference_price": "100",
            "currency": "USD",
        },
        "state": state,
        # fixed evaluation instant so the stale-state rules are deterministic
        "evaluated_at": "2026-10-07T12:00:30+00:00",
    }
    return body


def test_controls_roundtrip_and_defaults(client: TestClient, founder_headers):
    get = client.get("/api/accounts/acct-api/controls", headers=founder_headers)
    assert get.status_code == 200
    assert get.json() == {
        "account_id": "acct-api",
        "entries_paused": False,
        "cancel_entries_requested": False,
        "reduce_only": False,
        "flatten_authorized": False,
        "flatten_authorized_by": None,
        "flatten_valid_until": None,
    }

    put = client.put(
        "/api/accounts/acct-api/controls",
        headers=founder_headers,
        json={"entries_paused": True},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["entries_paused"] is True
    assert body["flatten_authorized"] is False, "a pause never implies flatten"


def test_flatten_needs_separate_authorization(client: TestClient, founder_headers):
    grant = client.post(
        "/api/accounts/acct-api/controls/flatten",
        headers=founder_headers,
        json={"authorized_by": "ops-alice", "minutes": 10},
    )
    assert grant.status_code == 200
    assert grant.json()["flatten_authorized"] is True
    assert grant.json()["flatten_authorized_by"] == "ops-alice"

    # a bulk control write must not clear the separate grant
    put = client.put(
        "/api/accounts/acct-api/controls",
        headers=founder_headers,
        json={"entries_paused": True},
    )
    assert put.json()["flatten_authorized"] is True

    cancel = client.post(
        "/api/accounts/acct-api/controls/flatten/cancel", headers=founder_headers
    )
    assert cancel.status_code == 200
    assert cancel.json()["flatten_authorized"] is False


def test_controls_are_tenant_scoped(client: TestClient, founder_headers, member_headers):
    client.put(
        "/api/accounts/acct-shared/controls",
        headers=founder_headers,
        json={"entries_paused": True},
    )
    other = client.get("/api/accounts/acct-shared/controls", headers=member_headers)
    assert other.status_code == 200
    assert other.json()["entries_paused"] is False, "another tenant sees its own (empty) controls"


def test_preview_is_deterministic_and_reserves_nothing(client: TestClient, founder_headers):
    first = client.post("/api/risk/preview", headers=founder_headers, json=_preview_body())
    assert first.status_code == 200
    body = first.json()["decision"]
    assert body["decision"] == "APPROVE"
    assert body["required_reservation"]["amount"] == "500.75"

    # same input → same decision; preview is pure
    second = client.post("/api/risk/preview", headers=founder_headers, json=_preview_body())
    assert second.json()["decision"] == first.json()["decision"]

    # over the order cap → deterministic clamp with the explicit rule
    over = _preview_body()
    over["proposal"]["quantity"] = "6"  # 600 still > 500
    clamped = client.post("/api/risk/preview", headers=founder_headers, json=over)
    decision = clamped.json()["decision"]
    assert decision["decision"] == "CLAMP"
    assert decision["rule"] == "max_order_notional"
    assert decision["approved_notional"]["amount"] == "500.00"

    # stale mark → new risk blocked
    stale = _preview_body(
        instrument_mark={
            "instrument_id": "KXA8.DEMO",
            "price": "100",
            "quality": "STALE_CACHE",
            "observed_at": "2026-10-07T11:00:00+00:00",
        }
    )
    denied = client.post("/api/risk/preview", headers=founder_headers, json=stale)
    body = denied.json()["decision"]
    assert body["decision"] == "DENY" and body["rule"] == "stale_state"


def test_preview_requires_auth(client: TestClient):
    assert client.post("/api/risk/preview", json=_preview_body()).status_code == 401
