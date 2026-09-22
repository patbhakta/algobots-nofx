"""Discipline mechanics — post-only entries, IOC exits, holds, supersession."""

from decimal import Decimal

from algobots.execution.discipline import ExecutionDiscipline
from algobots.execution.planner import (
    AccountState,
    DisciplineAnnotations,
    MarketState,
    OrderPlan,
    PlannedOrder,
)

TICK = Decimal("0.25")


def make_plan(orders, plan_hash="h1"):
    return OrderPlan(
        inputs_hash=plan_hash,
        market_closed=False,
        projected_turnover=Decimal("0"),
        turnover=Decimal("0"),
        scale_factor=Decimal("1"),
        orders=list(orders),
        unknown=[],
        gated_out=[],
        discipline=DisciplineAnnotations(),
    )


def entry(symbol, side, quantity=Decimal("10"), plan_hash="h1"):
    return PlannedOrder(
        symbol=symbol,
        side=side,
        quantity=quantity,
        notional=Decimal("1000"),
        intent="entry",
    )


def exit_order(symbol, side, quantity=Decimal("10"), plan_hash="h1"):
    return PlannedOrder(
        symbol=symbol,
        side=side,
        quantity=quantity,
        notional=Decimal("-1000") if side == "sell" else Decimal("1000"),
        intent="exit",
    )


def open_market(bid=Decimal("99"), ask=Decimal("101")):
    return MarketState(is_open=True, bid=bid, ask=ask)


ACCOUNT = AccountState(positions={"X": Decimal("50")})


def test_entry_buy_posts_one_tick_inside_the_touch():
    discipline = ExecutionDiscipline(tick_size=TICK)
    instruction = discipline.tick(
        make_plan([entry("X", "buy")]), open_market(), ACCOUNT
    )
    assert instruction.order_type == "post_only_limit"
    assert instruction.reduce_only is False
    assert instruction.limit_price == Decimal("100.75")
    assert instruction.plan_hash == "h1"


def test_entry_sell_posts_one_tick_inside_the_touch():
    discipline = ExecutionDiscipline(tick_size=TICK)
    instruction = discipline.tick(
        make_plan([entry("X", "sell")]), open_market(), ACCOUNT
    )
    assert instruction.order_type == "post_only_limit"
    assert instruction.limit_price == Decimal("99.25")


def test_exit_is_ioc_and_reduce_only():
    discipline = ExecutionDiscipline(tick_size=TICK)
    instruction = discipline.tick(
        make_plan([exit_order("X", "sell", quantity=Decimal("5"))]),
        open_market(),
        ACCOUNT,
    )
    assert instruction.order_type == "ioc"
    assert instruction.reduce_only is True
    assert instruction.limit_price is None
    assert instruction.quantity == Decimal("5")
    assert instruction.side == "sell"


def test_exit_quantity_never_exceeds_account_position():
    discipline = ExecutionDiscipline(tick_size=TICK)
    account = AccountState(positions={"X": Decimal("3")})
    instruction = discipline.tick(
        make_plan([exit_order("X", "sell", quantity=Decimal("10"))]),
        open_market(),
        account,
    )
    assert instruction.quantity == Decimal("3")


def test_exit_without_a_position_holds():
    discipline = ExecutionDiscipline(tick_size=TICK)
    account = AccountState(positions={})
    assert (
        discipline.tick(make_plan([exit_order("X", "sell")]), open_market(), account)
        is None
    )


def test_unknown_upstream_holds():
    discipline = ExecutionDiscipline(tick_size=TICK)
    market = MarketState(is_open=True, bid=Decimal("99"), ask=Decimal("101"), upstream_available=False)
    assert discipline.tick(make_plan([entry("X", "buy")]), market, ACCOUNT) is None


def test_unknown_quotes_hold():
    discipline = ExecutionDiscipline(tick_size=TICK)
    market = MarketState(is_open=True, bid=None, ask=None)
    assert discipline.tick(make_plan([entry("X", "buy")]), market, ACCOUNT) is None


def test_market_closed_holds_even_with_a_valid_plan():
    discipline = ExecutionDiscipline(tick_size=TICK)
    market = MarketState(is_open=False)
    assert discipline.tick(make_plan([entry("X", "buy")]), market, ACCOUNT) is None


def test_at_most_one_order_per_tick():
    discipline = ExecutionDiscipline(tick_size=TICK)
    plan = make_plan([entry("A", "buy"), entry("B", "sell")])
    first = discipline.tick(plan, open_market(), ACCOUNT)
    second = discipline.tick(plan, open_market(), ACCOUNT)
    third = discipline.tick(plan, open_market(), ACCOUNT)
    assert first.symbol == "A"
    assert second.symbol == "B"
    assert third is None


def test_newest_plan_supersedes_and_pulls_stale_orders():
    discipline = ExecutionDiscipline(tick_size=TICK)
    plan_a = make_plan([entry("A", "buy"), entry("B", "sell")], plan_hash="a")
    plan_b = make_plan([entry("C", "buy")], plan_hash="b")
    first = discipline.tick(plan_a, open_market(), ACCOUNT)
    second = discipline.tick(plan_b, open_market(), ACCOUNT)
    third = discipline.tick(plan_b, open_market(), ACCOUNT)
    assert first.symbol == "A"
    assert second.symbol == "C"
    assert third is None


def test_hold_pulls_stale_queued_orders():
    discipline = ExecutionDiscipline(tick_size=TICK)
    plan = make_plan([entry("A", "buy"), entry("B", "sell")])
    assert discipline.tick(plan, open_market(), ACCOUNT).symbol == "A"
    assert discipline.tick(None, open_market(), ACCOUNT) is None
    assert discipline.tick(make_plan([]), open_market(), ACCOUNT) is None
    pulled = discipline.tick(plan, open_market(), ACCOUNT)
    assert pulled.symbol == "A"


def test_tick_size_is_required_positive():
    import pytest

    with pytest.raises(ValueError):
        ExecutionDiscipline(tick_size=Decimal("0"))
