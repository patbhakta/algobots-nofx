"""Governor properties — turnover ≤ cap, never rejects, sells ≤ holdings."""

from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from algobots.execution.governor import TurnoverGovernor
from algobots.execution.planner import (
    MarketState,
    PlannerConfig,
    PlannedOrder,
    Position,
    plan_orders,
)
from algobots.execution.quantity import QTY_QUANT

SYMBOLS = ["A", "B", "C", "D", "E"]

quantities = st.integers(min_value=-100000, max_value=100000).map(
    lambda n: Decimal(n) / 10
)
prices = st.integers(min_value=1, max_value=1000000).map(
    lambda n: Decimal(n) / 100
)
weights = st.integers(min_value=-150, max_value=150).map(
    lambda n: Decimal(n) / 100
)
navs = st.integers(min_value=100, max_value=10000000).map(
    lambda n: Decimal(n) / 100
)
caps = st.integers(min_value=1, max_value=1000).map(lambda n: Decimal(n) / 1000)


@st.composite
def portfolios(draw):
    count = draw(st.integers(min_value=1, max_value=5))
    chosen = draw(st.permutations(SYMBOLS))[0:count]
    target_weights = {}
    holdings = {}
    for symbol in chosen:
        target_weights[symbol] = draw(weights)
        holdings[symbol] = Position(
            symbol=symbol,
            quantity=draw(quantities),
            price=draw(prices),
        )
    return target_weights, holdings, draw(navs), draw(caps)


@given(portfolios())
@settings(max_examples=250, deadline=None)
def test_governor_properties_hold_for_arbitrary_inputs(case):
    target_weights, holdings, nav, cap = case
    plan = plan_orders(
        target_weights,
        holdings,
        MarketState(is_open=True),
        PlannerConfig(nav=nav, turnover_cap=cap),
    )

    assert plan.turnover <= cap
    assert plan.turnover <= plan.projected_turnover
    assert plan.scale_factor <= 1

    for order in plan.orders:
        held = holdings[order.symbol].quantity
        if order.side == "sell":
            assert held <= 0 or order.quantity <= held
        else:
            assert held >= 0 or order.quantity <= -held
        assert order.quantity >= QTY_QUANT


@given(portfolios())
@settings(max_examples=250, deadline=None)
def test_governor_never_rejects(case):
    target_weights, holdings, nav, cap = case
    governor = TurnoverGovernor(turnover_cap=cap, nav=nav)
    current = {symbol: p.quantity for symbol, p in holdings.items()}
    prices = {symbol: p.price for symbol, p in holdings.items()}
    planned = [
        PlannedOrder(
            symbol=symbol,
            side="buy" if target_weights[symbol] >= 0 else "sell",
            quantity=(abs(target_weights[symbol]) * nav / prices[symbol]).quantize(
                Decimal("0.00000001")
            ),
            notional=target_weights[symbol] * nav,
            intent="entry",
        )
        for symbol in target_weights
    ]
    result = governor.apply(planned, current=current, prices=prices)
    assert result.turnover <= cap
    assert result.scale_factor <= 1
