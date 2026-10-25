"""Frozen decisions use settled history and produce bounded gateway requests."""

import json
from decimal import Decimal

import pytest
from tests.deployments.test_runtime import account, deployment

from algobots.api.deployments.momentum import momentum_intent
from algobots.node.kalshi import KalshiObservation
from algobots.strategies.studio import compile_studio_strategy, parse_draft


def rows():
    return [
        {"outcome": 1, "settle_value": str(100 + i * i), "close_ts": 900 * (i + 1)}
        for i in range(22)
    ]


def intent(d=None, history=None, book=None):
    d = d or configured_deployment()
    return momentum_intent(
        d,
        account(d),
        history if history is not None else rows(),
        book
        or KalshiObservation(1, 20000 * 10**9, "KXBTC15M-TEST", Decimal(".40"), Decimal(".45")),
        now_ns=20001 * 10**9,
    )


def configured_deployment():
    d = deployment()
    draft = json.loads(d.frozen_spec["artifact"]["canonical_draft"])
    draft["decision"]["min_confidence"] = 0.1
    artifact = compile_studio_strategy(parse_draft(draft)).model_dump(mode="json")
    d.artifact_hash = artifact["artifact_hash"]
    d.frozen_spec["artifact"] = artifact
    d.frozen_spec["studio_evidence"]["artifact_hash"] = d.artifact_hash
    return d


def test_frozen_decision_is_stable_and_risk_bounded():
    d = configured_deployment()
    result = intent(d)
    assert result is not None
    assert result == intent(d)
    assert result.body["side"] == "buy"
    assert Decimal(result.body["qty"]) * Decimal(".45") <= Decimal(d.max_order_value)
    assert result.body["order_type"] == "limit"
    assert result.body["limit_px"] == "0.45"
    assert result.body["account_id"] == str(d.account_id)


def test_insufficient_history_abstains():
    assert intent(history=rows()[:4]) is None


@pytest.mark.parametrize("bid,ask", [("NaN", ".5"), (".6", ".5"), ("0", ".5"), (".4", "1")])
def test_invalid_binary_book_abstains(bid, ask):
    assert (
        intent(
            book=KalshiObservation(1, 20000 * 10**9, "KXBTC15M-TEST", Decimal(bid), Decimal(ask))
        )
        is None
    )


def test_stale_book_abstains():
    assert (
        intent(book=KalshiObservation(1, 1, "KXBTC15M-TEST", Decimal(".4"), Decimal(".5"))) is None
    )


def test_wrong_market_abstains():
    assert (
        intent(book=KalshiObservation(1, 20000 * 10**9, "OTHER", Decimal(".4"), Decimal(".5")))
        is None
    )


def test_tampered_frozen_snapshot_refused():
    d = deployment()
    d.frozen_spec["artifact"]["nautilus"]["params"]["min_edge"] = 0
    with pytest.raises(ValueError):
        intent(d)


def test_future_settlements_are_excluded():
    assert intent(history=[{**r, "close_ts": r["close_ts"] + 20000} for r in rows()]) is None


def test_gapped_history_abstains():
    assert intent(history=rows()[:10] + rows()[15:]) is None


def test_zero_cap_is_refused():
    d = configured_deployment()
    d.max_order_value = "0"
    with pytest.raises(ValueError):
        intent(d)
