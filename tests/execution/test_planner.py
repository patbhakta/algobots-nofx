"""Planner policy units — sell-to-zero, unknowns, hashing, market closed."""

from decimal import Decimal

from algobots.execution.planner import (
    MarketState,
    PlannerConfig,
    Position,
    plan_orders,
)

NAV = Decimal("100000")
CAP = Decimal("0.50")


def config(**overrides):
    kwargs = {"nav": NAV, "turnover_cap": CAP}
    kwargs.update(overrides)
    return PlannerConfig(**kwargs)


def open_market():
    return MarketState(is_open=True)


def test_target_absent_liquidates_full_position():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("7"), price=Decimal("10")),
    }
    plan = plan_orders({}, holdings, open_market(), config())
    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert (order.side, order.quantity, order.intent) == ("sell", Decimal("7"), "exit")
    assert order.notional == Decimal("-70")


def test_negative_target_liquidates_never_shorts():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("20"), price=Decimal("100")),
    }
    plan = plan_orders({"X": Decimal("-0.50")}, holdings, open_market(), config())
    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert (order.side, order.quantity, order.intent) == ("sell", Decimal("20"), "exit")
    assert order.notional == Decimal("-2000")


def test_covering_buy_never_exceeds_short_leg():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("-9"), price=Decimal("50")),
    }
    plan = plan_orders({"X": Decimal("0")}, holdings, open_market(), config())
    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert (order.side, order.quantity, order.intent) == ("buy", Decimal("9"), "exit")
    assert order.notional == Decimal("450")


def test_sell_never_exceeds_holdings_on_sign_flip():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("5"), price=Decimal("10")),
    }
    plan = plan_orders({"X": Decimal("-0.50")}, holdings, open_market(), config())
    assert len(plan.orders) == 1
    order = plan.orders[0]
    assert order.side == "sell"
    assert order.quantity == Decimal("5")
    assert order.intent == "exit"


def test_unknown_price_symbol_produces_no_order_and_is_listed():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("5"), price=Decimal("10")),
        "Y": Position(symbol="Y", quantity=Decimal("5"), price=None),
        "Z": Position(symbol="Z", quantity=Decimal("5"), price=Decimal("9"), tradable=False),
    }
    plan = plan_orders({"X": Decimal("0.10")}, holdings, open_market(), config())
    assert plan.unknown == ["Y", "Z"]
    assert [o.symbol for o in plan.orders] == ["X"]


def test_inputs_hash_is_stable_and_sensitive():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("5"), price=Decimal("10")),
    }
    plan_a = plan_orders({"X": Decimal("0.10")}, holdings, open_market(), config())
    plan_b = plan_orders({"X": Decimal("0.10")}, holdings, open_market(), config())
    plan_c = plan_orders({"X": Decimal("0.20")}, holdings, open_market(), config())
    assert plan_a.inputs_hash == plan_b.inputs_hash
    assert plan_a.inputs_hash != plan_c.inputs_hash
    assert len(plan_a.inputs_hash) == 64


def test_market_closed_emits_full_plan_annotated_next_open():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("5"), price=Decimal("10")),
    }
    market = MarketState(
        is_open=False, next_open="2026-09-23T13:30:00+00:00"
    )
    plan = plan_orders({"X": Decimal("0.10")}, holdings, market, config())
    assert plan.market_closed is True
    assert plan.dispatch_at == "2026-09-23T13:30:00+00:00"
    assert len(plan.orders) == 1


def test_market_open_has_no_dispatch_annotation():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("5"), price=Decimal("10")),
    }
    plan = plan_orders({"X": Decimal("0.10")}, holdings, open_market(), config())
    assert plan.market_closed is False
    assert plan.dispatch_at is None


def test_zero_delta_produces_no_order():
    holdings = {
        "X": Position(symbol="X", quantity=Decimal("50"), price=Decimal("200")),
    }
    plan = plan_orders({"X": Decimal("0.10")}, holdings, open_market(), config())
    assert plan.orders == []
    assert plan.turnover == 0
    assert plan.scale_factor == 1
