"""Dry-run proof — plan_orders must make zero network calls."""

from decimal import Decimal

import pytest

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


@pytest.fixture(autouse=True)
def ban_sockets(monkeypatch):
    def _boom(*args, **kwargs):
        raise AssertionError("network access attempted during planning")

    monkeypatch.setattr("socket.socket", _boom)
    monkeypatch.setattr("socket.create_connection", _boom)
    monkeypatch.setattr("socket.getaddrinfo", _boom)


def test_plan_orders_makes_no_network_calls_with_risk_gate():
    gate = RiskGate(
        limits=RiskLimits(max_position_pct=0.25, max_gross_exposure=1.0),
        envelope=RiskEnvelope(
            max_order_value=Decimal("1000"), max_daily_loss=Decimal("500")
        ),
        breakers=RateBreakers(clock=lambda: 0.0),
        sink=InMemorySink(),
        now=lambda: "2026-09-22T00:00:00+00:00",
    )
    target_weights = {"AAPL": Decimal("0.10"), "GOOG": Decimal("0")}
    holdings = {
        "AAPL": Position(symbol="AAPL", quantity=Decimal("100"), price=Decimal("200")),
        "GOOG": Position(symbol="GOOG", quantity=Decimal("10"), price=Decimal("100")),
    }
    closed = MarketState(is_open=False, next_open="2026-09-23T13:30:00+00:00")
    plan = plan_orders(
        target_weights,
        holdings,
        closed,
        PlannerConfig(
            nav=Decimal("100000"), turnover_cap=Decimal("0.20"), risk_gate=gate
        ),
    )
    assert plan.market_closed is True
    assert len(plan.orders) == 2
