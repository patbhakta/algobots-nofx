"""A09 acceptance case 3 (fixture half): deterministic synthetic fixtures, all marked DEMO DATA."""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from algobots.dashboard.fixtures import DEMO_LABEL, STATES, all_fixtures, fixture

ROOT = Path(__file__).resolve().parents[3]
EXPORTED = ROOT / "artifacts" / "A09" / "fixtures"


def _walk(node, path=""):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from _walk(v, f"{path}[{i}]")


def test_exactly_the_five_required_states():
    assert STATES == ("good", "loss", "empty", "stale", "unknown")
    with pytest.raises(KeyError):
        fixture("profit")


def test_fixtures_are_deterministic_and_exported_copies_are_current():
    assert all_fixtures() == all_fixtures()
    for state, data in all_fixtures().items():
        on_disk = json.loads((EXPORTED / f"{state}.json").read_text())
        assert on_disk == data, f"artifacts/A09/fixtures/{state}.json is stale; rebuild"


@pytest.mark.parametrize("state", STATES)
def test_every_fixture_is_marked_synthetic(state):
    f = fixture(state)
    assert f["synthetic"] is True and f["label"] == DEMO_LABEL == "DEMO DATA"
    for acct in f["accounts"]:
        assert acct["id"].startswith("demo-") and acct["broker"] == "SIMULATED"
        assert acct["environment"] in ("PAPER", "LIVE")
        assert "(demo" in acct["label"]


@pytest.mark.parametrize("state", STATES)
def test_amounts_are_decimal_strings_with_currency(state):
    seen = 0
    for path, node in _walk(fixture(state)):
        if "amount" in node:
            seen += 1
            assert isinstance(node["amount"], str), path
            Decimal(node["amount"])
            assert node["currency"] in ("USD", "EUR"), path
    assert seen > 0


@pytest.mark.parametrize("state", STATES)
def test_missing_values_are_none_with_reason_never_zero_or_infinite(state):
    f = fixture(state)
    text = json.dumps(f)
    assert "Infinity" not in text and "NaN" not in text
    for name, s in f["stats"].items():
        if isinstance(s, dict):
            assert (s["value"] is None) == bool(s["unavailable_reason"]), (state, name)


def test_state_semantics():
    good, loss, empty, stale, unknown = (fixture(s) for s in STATES)
    assert Decimal(good["portfolio"]["net_pnl"]["amount"]) > 0
    assert Decimal(loss["portfolio"]["net_pnl"]["amount"]) < 0
    assert any(e["kind"] == "drawdown" for e in loss["exceptions"])
    assert any(p["error"] for p in loss["studio"]["params"]), "field-level validation failure"
    assert empty["positions"] == [] and empty["orders"] == [] and empty["stats"]["sample"] == 0
    assert all(
        empty["stats"][k]["value"] is None for k in ("win_rate_pct", "sharpe", "profit_factor")
    )
    assert stale["feed"]["status"] == "disconnected" and stale["feed"]["age_s"] > 60
    assert stale["invite"]["status"] == "expired"
    assert unknown["portfolio"]["equity"] is None
    assert any(o["status"] == "UNKNOWN" for o in unknown["orders"])
    assert unknown["depth"]["entitled"] is False
    outcomes = {n["outcome"] for f in (good, unknown) for n in f["topology"]}
    assert outcomes >= {
        "APPROVED",
        "REJECTED",
        "AWAITING_APPROVAL",
        "ABSTAIN",
        "UNKNOWN",
        "RECONCILING",
    }


def test_mixed_currency_and_paper_live_distinction_present():
    f = fixture("good")
    assert {a["currency"] for a in f["accounts"]} == {"USD", "EUR"}
    assert {a["environment"] for a in f["accounts"]} == {"PAPER", "LIVE"}
