"""Golden-file tests — fixture portfolios produce byte-exact artifacts."""

from decimal import Decimal
from pathlib import Path

import pytest

from algobots.execution.planner import (
    MarketState,
    PlannerConfig,
    Position,
    plan_orders,
)

GOLDEN_DIR = Path(__file__).parent / "golden"


def long_only_rebalance():
    """Partial rebalance + a no-target liquidation + an unknown-price name.

    Projected turnover 0.26 > cap 0.20, so the golden artifact also pins
    the governor's scale-down arithmetic.
    """
    target_weights = {"AAPL": Decimal("0.10"), "MSFT": Decimal("0.20")}
    holdings = {
        "AAPL": Position(symbol="AAPL", quantity=Decimal("100"), price=Decimal("200")),
        "MSFT": Position(symbol="MSFT", quantity=Decimal("20"), price=Decimal("250")),
        "GOOG": Position(symbol="GOOG", quantity=Decimal("10"), price=Decimal("100")),
        "TSLA": Position(symbol="TSLA", quantity=Decimal("3"), price=None),
    }
    return target_weights, holdings, Decimal("100000"), Decimal("0.20")


def flat_short_flip():
    """Flip toward a short book, executed as sell-to-zero per policy.

    DOG has no target (liquidate), OWL is short with target 0 (buy back to
    zero), CAT is long with a negative target (sell-to-zero — targets ≤ 0
    never enter shorts, they liquidate), BAT is a fresh long entry.
    """
    target_weights = {
        "CAT": Decimal("-0.05"),
        "OWL": Decimal("0"),
        "BAT": Decimal("0.10"),
    }
    holdings = {
        "DOG": Position(symbol="DOG", quantity=Decimal("100"), price=Decimal("50")),
        "CAT": Position(symbol="CAT", quantity=Decimal("20"), price=Decimal("100")),
        "OWL": Position(symbol="OWL", quantity=Decimal("-10"), price=Decimal("200")),
        "BAT": Position(symbol="BAT", quantity=Decimal("0"), price=Decimal("100")),
    }
    return target_weights, holdings, Decimal("50000"), Decimal("0.50")


def already_at_target():
    """Exact positions plus sub-precision dust → a no-op plan."""
    target_weights = {"AAPL": Decimal("0.10"), "MSFT": Decimal("0.10")}
    holdings = {
        "AAPL": Position(symbol="AAPL", quantity=Decimal("50"), price=Decimal("200")),
        "MSFT": Position(
            symbol="MSFT", quantity=Decimal("100.000000001"), price=Decimal("100")
        ),
    }
    return target_weights, holdings, Decimal("100000"), Decimal("0.10")


FIXTURES = {
    "long_only_rebalance": long_only_rebalance,
    "flat_short_flip": flat_short_flip,
    "already_at_target": already_at_target,
}


def build_plan(name):
    target_weights, holdings, nav, cap = FIXTURES[name]()
    market = MarketState(is_open=True)
    config = PlannerConfig(nav=nav, turnover_cap=cap)
    return plan_orders(target_weights, holdings, market, config)


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_artifact_is_byte_exact_against_golden(name):
    plan = build_plan(name)
    expected = (GOLDEN_DIR / f"{name}.json").read_text(encoding="utf-8")
    assert plan.model_dump_json() == expected
