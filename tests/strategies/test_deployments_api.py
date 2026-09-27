"""Deployment API acceptance tests (AC 2-5: freeze, duplicate guard, breakers).

Freeze proof (AC 2): after deploy, PATCHing the strategy (name + params)
leaves the deployment's frozen spec and artifact hash byte-identical, and the
frozen spec still evaluates with the OLD parameters on bars where the edited
parameters would flip the signal.
"""

import logging
from decimal import Decimal

from algobots.strategies.dsl import artifact_hash, validate_spec
from algobots.strategies.eval import bars_from_closes, evaluate

# Crossover fixture (hand-computed in test_eval.py): sma2 crosses_above sma3
# on the last bar; sma4 does NOT.
CROSSOVER_CLOSES = [10, 11, 12, 13, 8, 9, 11]

DSL_PARAMS = {
    "version": 1,
    "cadence": "5m",
    "entry": {
        "left": {"indicator": "sma", "params": {"period": 2}},
        "op": "crosses_above",
        "right": {"indicator": "sma", "params": {"period": 3}},
    },
    "exit": {
        "left": {"indicator": "sma", "params": {"period": 2}},
        "op": "crosses_below",
        "right": {"indicator": "sma", "params": {"period": 3}},
    },
}


def _make_account(client, headers, label="Main") -> dict:
    response = client.post(
        "/api/accounts", headers=headers, json={"label": label, "broker": "alpaca"}
    )
    assert response.status_code == 201, response.text
    return response.json()


def _make_dsl_strategy(client, headers, name="MA cross", params=None) -> dict:
    response = client.post(
        "/api/strategies",
        headers=headers,
        json={"name": name, "kind": "condition_dsl", "params": params or DSL_PARAMS},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _deploy(client, headers, strategy_id, account_id, symbol="AAPL", **overrides) -> dict:
    body = {
        "strategy_id": strategy_id,
        "account_id": account_id,
        "symbol": symbol,
        "max_order_value": "1000.00",
        "max_daily_loss": "500.00",
        **overrides,
    }
    response = client.post("/api/deployments", headers=headers, json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --- create + freeze snapshot --------------------------------------------------


def test_create_freezes_spec_envelope_and_hash(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    dep = _deploy(client, member_headers, strategy["id"], account["id"], symbol="aapl")

    assert dep["symbol"] == "AAPL"  # normalized
    assert dep["status"] == "running"
    assert dep["effective_state"] == "running"
    # The frozen snapshot is the NORMALIZED spec (defaults like source/version
    # filled in) — the canonical artifact the hash is computed over.
    assert dep["frozen_spec"] == {
        "name": "MA cross",
        "kind": "condition_dsl",
        "spec": validate_spec(DSL_PARAMS).model_dump(mode="json"),
    }
    assert dep["artifact_hash"] == artifact_hash(validate_spec(DSL_PARAMS))
    assert Decimal(dep["max_order_value"]) == Decimal("1000.00")
    assert Decimal(dep["max_daily_loss"]) == Decimal("500.00")
    assert dep["breaker_state"] == "closed"


def test_freeze_survives_strategy_edit(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    dep = _deploy(client, member_headers, strategy["id"], account["id"])
    frozen_before = dep["frozen_spec"]
    hash_before = dep["artifact_hash"]

    edited_params = {
        **DSL_PARAMS,
        "entry": {
            "left": {"indicator": "sma", "params": {"period": 4}},  # 2 → 4
            "op": "crosses_above",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
    }
    patched = client.patch(
        f"/api/strategies/{strategy['id']}",
        headers=member_headers,
        json={"name": "MA cross v2", "params": edited_params},
    )
    assert patched.status_code == 200, patched.text

    after = client.get(f"/api/deployments/{dep['id']}", headers=member_headers)
    assert after.status_code == 200
    body = after.json()
    assert body["frozen_spec"] == frozen_before  # snapshot untouched
    assert body["artifact_hash"] == hash_before  # identity untouched

    # Behavioral proof: the frozen (period 2) spec still fires on the fixture
    # bars, while the edited (period 4) spec would not — the deployment runs
    # the frozen copy.
    frozen = validate_spec(body["frozen_spec"]["spec"])
    edited = validate_spec(edited_params)
    bars = bars_from_closes(CROSSOVER_CLOSES)
    assert evaluate(frozen, bars).entry is True
    assert evaluate(edited, bars).entry is False


# --- duplicate-deployment guard (AC 4 / A11 case 4) -----------------------------


def test_duplicate_tuple_rejected_409_with_clear_message(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    _deploy(client, member_headers, strategy["id"], account["id"], symbol="AAPL")

    dup = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": strategy["id"],
            "account_id": account["id"],
            "symbol": "aapl",  # case must not dodge the guard
            "max_order_value": "1000.00",
            "max_daily_loss": "500.00",
        },
    )
    assert dup.status_code == 409
    assert "already exists" in dup.json()["detail"]
    assert "AAPL" in dup.json()["detail"]


def test_same_tuple_different_symbol_or_account_ok(client, member_headers):
    account = _make_account(client, member_headers)
    other = _make_account(client, member_headers, label="Second")
    strategy = _make_dsl_strategy(client, member_headers)
    _deploy(client, member_headers, strategy["id"], account["id"], symbol="AAPL")
    assert (
        _deploy(client, member_headers, strategy["id"], account["id"], symbol="TSLA")["symbol"]
        == "TSLA"
    )
    _deploy(client, member_headers, strategy["id"], other["id"], symbol="AAPL")

    listed = client.get("/api/deployments", headers=member_headers).json()
    assert len([d for d in listed if d["status"] == "running"]) == 3


def test_stopped_deployment_frees_the_tuple(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    dep = _deploy(client, member_headers, strategy["id"], account["id"])
    stopped = client.patch(
        f"/api/deployments/{dep['id']}", headers=member_headers, json={"status": "stopped"}
    )
    assert stopped.status_code == 200
    _deploy(client, member_headers, strategy["id"], account["id"])  # no 409 now


# --- per-deployment envelope breach trips ONLY that deployment (AC 3) -----------


def test_envelope_breach_trips_only_that_deployment(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    a = _deploy(client, member_headers, strategy["id"], account["id"], symbol="AAPL")
    b = _deploy(client, member_headers, strategy["id"], account["id"], symbol="TSLA")

    ok = client.post(
        f"/api/deployments/{a['id']}/risk/daily-loss",
        headers=member_headers,
        json={"daily_pnl": "-400.00"},  # under the 500 cap
    )
    assert ok.status_code == 200
    assert ok.json()["tripped"] is False
    assert ok.json()["effective_state"] == "running"

    breached = client.post(
        f"/api/deployments/{a['id']}/risk/daily-loss",
        headers=member_headers,
        json={"daily_pnl": "-500.00"},  # loss == cap trips (conservative)
    )
    assert breached.status_code == 200
    assert breached.json()["tripped"] is True

    halted = client.get(f"/api/deployments/{a['id']}", headers=member_headers).json()
    assert halted["breaker_state"] == "open"
    assert halted["effective_state"] == "halted"
    assert halted["halt_source"] == "deployment_breaker"
    assert "500" in halted["breaker_reason"]

    sibling = client.get(f"/api/deployments/{b['id']}", headers=member_headers).json()
    assert sibling["effective_state"] == "running"
    assert sibling["breaker_state"] == "closed"

    # Reset reopens just this deployment.
    reset = client.post(f"/api/deployments/{a['id']}/breaker/reset", headers=member_headers)
    assert reset.status_code == 200
    assert reset.json()["breaker_state"] == "closed"
    assert reset.json()["effective_state"] == "running"


# --- fleet breaker halts EVERY deployment in scope (AC 3) ------------------------


def test_fleet_breaker_halts_every_deployment_in_scope(client, member_headers, founder_headers):
    member_account = _make_account(client, member_headers)
    founder_account = _make_account(client, founder_headers, label="Founder")
    member_strategy = _make_dsl_strategy(client, member_headers)
    founder_strategy = _make_dsl_strategy(client, founder_headers)

    m1 = _deploy(client, member_headers, member_strategy["id"], member_account["id"], "AAPL")
    m2 = _deploy(client, member_headers, member_strategy["id"], member_account["id"], "TSLA")
    f1 = _deploy(client, founder_headers, founder_strategy["id"], founder_account["id"], "MSFT")

    trip = client.post(
        "/api/deployments/fleet/breaker",
        headers=member_headers,
        json={"action": "trip", "reason": "risk desk drill"},
    )
    assert trip.status_code == 200
    assert trip.json()["state"] == "open"

    for dep in (m1, m2):  # every deployment in the member's scope is halted
        state = client.get(f"/api/deployments/{dep['id']}", headers=member_headers).json()
        assert state["effective_state"] == "halted"
        assert state["halt_source"] == "fleet_breaker"
        assert state["breaker_state"] == "closed"  # own breaker untouched

    outsider = client.get(f"/api/deployments/{f1['id']}", headers=founder_headers).json()
    assert outsider["effective_state"] == "running"  # scope is per user

    reset = client.post(
        "/api/deployments/fleet/breaker", headers=member_headers, json={"action": "reset"}
    )
    assert reset.status_code == 200 and reset.json()["state"] == "closed"
    for dep in (m1, m2):
        resumed = client.get(f"/api/deployments/{dep['id']}", headers=member_headers).json()
        assert resumed["effective_state"] == "running"

    fleet_state = client.get("/api/deployments/fleet/breaker", headers=member_headers)
    assert fleet_state.status_code == 200
    assert fleet_state.json()["state"] == "closed"


# --- validation + tenancy ---------------------------------------------------------


def test_deploy_rejects_invalid_dsl_with_422(client, member_headers):
    account = _make_account(client, member_headers)

    garbage = client.post(
        "/api/strategies",
        headers=member_headers,
        json={"name": "Broken", "kind": "condition_dsl", "params": {"foo": 1}},
    ).json()
    invalid = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": garbage["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "1000",
            "max_daily_loss": "500",
        },
    )
    assert invalid.status_code == 422

    unknown_indicator = dict(DSL_PARAMS)
    unknown_indicator["entry"] = {
        "left": {"indicator": "hma", "params": {"period": 2}},
        "op": "gt",
        "right": {"value": 1},
    }
    hma = client.post(
        "/api/strategies",
        headers=member_headers,
        json={"name": "HMA", "kind": "condition_dsl", "params": unknown_indicator},
    ).json()
    response = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": hma["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "1000",
            "max_daily_loss": "500",
        },
    )
    assert response.status_code == 422
    assert "indicator" in response.json()["detail"]

    plain = client.post(
        "/api/strategies",
        headers=member_headers,
        json={"name": "Legacy", "kind": "mean_reversion", "params": {"lookback": 20}},
    ).json()
    wrong_kind = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": plain["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "1000",
            "max_daily_loss": "500",
        },
    )
    assert wrong_kind.status_code == 422
    assert "condition_dsl" in wrong_kind.json()["detail"]


def test_envelope_caps_required_and_positive(client, member_headers):
    account = _make_account(client, member_headers)
    strategy = _make_dsl_strategy(client, member_headers)
    missing = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": strategy["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "1000",
        },
    )
    assert missing.status_code == 422
    zero = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": strategy["id"],
            "account_id": account["id"],
            "symbol": "AAPL",
            "max_order_value": "0",
            "max_daily_loss": "500",
        },
    )
    assert zero.status_code == 422


def test_tenant_isolation_on_deployments(client, member_headers, founder_headers):
    member_account = _make_account(client, member_headers)
    founder_account = _make_account(client, founder_headers, label="Founder-isolation")
    founder_strategy = _make_dsl_strategy(client, founder_headers)
    dep = _deploy(client, founder_headers, founder_strategy["id"], founder_account["id"])

    # Cross-tenant references are indistinguishable from missing (404).
    cross = client.post(
        "/api/deployments",
        headers=member_headers,
        json={
            "strategy_id": founder_strategy["id"],
            "account_id": member_account["id"],
            "symbol": "AAPL",
            "max_order_value": "10",
            "max_daily_loss": "5",
        },
    )
    assert cross.status_code == 404
    for method, path in [
        ("GET", f"/api/deployments/{dep['id']}"),
        ("PATCH", f"/api/deployments/{dep['id']}"),
        ("DELETE", f"/api/deployments/{dep['id']}"),
        ("POST", f"/api/deployments/{dep['id']}/risk/daily-loss"),
    ]:
        response = client.request(
            method,
            path,
            headers=member_headers,
            json={"daily_pnl": "-1"}
            if "risk" in path
            else ({"status": "stopped"} if method == "PATCH" else None),
        )
        assert response.status_code == 404, (method, response.status_code)

    listed = client.get("/api/deployments", headers=member_headers).json()
    assert dep["id"] not in [d["id"] for d in listed]


# --- observability: secret-free structured events (AC 5c) -------------------------


def test_structured_events_logged_secret_free(client, member_headers, caplog):
    with caplog.at_level(logging.INFO, logger="algobots.api.deployments.service"):
        account = _make_account(client, member_headers)
        strategy = _make_dsl_strategy(client, member_headers)
        dep = _deploy(client, member_headers, strategy["id"], account["id"])
        client.post(
            f"/api/deployments/{dep['id']}/risk/daily-loss",
            headers=member_headers,
            json={"daily_pnl": "-900"},
        )
        client.post(
            "/api/deployments/fleet/breaker", headers=member_headers, json={"action": "trip"}
        )

    messages = [record.getMessage() for record in caplog.records]
    joined = " | ".join(messages)
    assert any(m.startswith("deployment_created") for m in messages)
    assert any(m.startswith("deployment_breaker_tripped") for m in messages)
    assert any(m.startswith("fleet_breaker_tripped") for m in messages)
    assert dep["id"] in joined and dep["artifact_hash"] in joined and "AAPL" in joined
    # Secret-free: no credential-shaped material ever appears.
    for marker in ("api_key", "api_secret", "api-key", "Authorization"):
        assert marker not in joined
