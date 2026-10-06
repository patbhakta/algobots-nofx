"""Integration — planner orders pass through the S1.2 risk rail."""

from decimal import Decimal

from algobots.execution.planner import (
    MarketState,
    PlannerConfig,
    Position,
    plan_orders,
)
from algobots.risk.audit import InMemorySink, RiskGate
from algobots.risk.breakers import RateBreakers
from algobots.risk.envelopes import RiskEnvelope
from algobots.risk.limits import RiskLimits

LIMITS = RiskLimits(max_position_pct=0.25, max_gross_exposure=1.0)
ENVELOPE = RiskEnvelope(
    max_order_value=Decimal("1000"), max_daily_loss=Decimal("500")
)


def make_gate(sink):
    return RiskGate(
        limits=LIMITS,
        envelope=ENVELOPE,
        breakers=RateBreakers(clock=lambda: 0.0),
        sink=sink,
        now=lambda: "2026-09-22T00:00:00+00:00",
    )


def test_entry_above_max_order_value_is_clamped_with_exactly_one_audit_row():
    sink = InMemorySink()
    gate = make_gate(sink)
    target_weights = {"NVDA": Decimal("0.05")}
    holdings = {
        "NVDA": Position(symbol="NVDA", quantity=Decimal("0"), price=Decimal("100"))
    }
    plan = plan_orders(
        target_weights,
        holdings,
        MarketState(is_open=True),
        PlannerConfig(
            nav=Decimal("100000"),
            turnover_cap=Decimal("0.10"),
            risk_gate=gate,
        ),
    )

    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert order.notional == Decimal("1000")
    assert order.quantity == Decimal("10")
    assert order.clamp is not None
    assert order.clamp.limit == "max_order_value"
    assert order.clamp.before == Decimal("5000")
    assert order.clamp.after == Decimal("1000")

    assert len(sink.rows) == 1
    row = sink.rows[0]
    assert row.source == "envelope"
    assert row.limit == "max_order_value"
    assert row.ticker == "NVDA"
    assert row.before == 5000.0
    assert row.after == 1000.0


def test_exits_are_privileged_and_never_clamped():
    sink = InMemorySink()
    gate = make_gate(sink)
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("1000"), price=Decimal("10"))
    }
    plan = plan_orders(
        {},
        holdings,
        MarketState(is_open=True),
        PlannerConfig(
            nav=Decimal("100000"),
            turnover_cap=Decimal("0.50"),
            risk_gate=gate,
        ),
    )

    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert order.intent == "exit"
    assert order.notional == Decimal("-10000")
    assert order.clamp is None
    assert len(sink.rows) == 0
