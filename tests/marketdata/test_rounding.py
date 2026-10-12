"""A05 acceptance case 2: tick/lot rounding matches the instrument; residuals explicit."""

from __future__ import annotations

from decimal import Decimal

from algobots.instruments import default_registry, round_price, round_quantity


def test_equity_price_rounds_to_nearest_cent_with_residual():
    aapl = default_registry().get("XNAS:equity:AAPL")
    rounded = round_price(aapl, Decimal("227.755"))
    assert rounded.value == Decimal("227.76")  # half-even
    assert rounded.residual == Decimal("-0.005")  # rounded up: residual negative
    assert rounded.increments == 22776

    down = round_price(aapl, Decimal("227.754"))
    assert down.value == Decimal("227.75")
    assert down.residual == Decimal("0.004")


def test_kraken_tick_coarser_than_coinbase_rounds_differently():
    registry = default_registry()
    fine = round_price(registry.get("COINBASE:spot-crypto:BTC-USD"), Decimal("61000.14"))
    coarse = round_price(registry.get("KRAKEN:spot-crypto:BTC-USD"), Decimal("61000.14"))
    assert fine.value == Decimal("61000.14")  # 0.01 tick
    assert coarse.value == Decimal("61000.10")  # 0.1 tick, half-even on .14 -> .1
    assert coarse.residual == Decimal("0.04")


def test_share_quantities_round_down_to_whole_lots():
    aapl = default_registry().get("XNAS:equity:AAPL")
    rounded = round_quantity(aapl, Decimal("10.5"))
    assert rounded.value == Decimal("10")
    assert rounded.residual == Decimal("0.5")  # the 0.5 share is explicit, never dropped
    assert rounded.increments == 10


def test_btc_satoshi_lot_never_rounds_quantity_up():
    btc = default_registry().get("COINBASE:spot-crypto:BTC-USD")
    rounded = round_quantity(btc, Decimal("0.123456789"))
    assert rounded.value == Decimal("0.12345678")
    assert rounded.residual == Decimal("0.000000009")


def test_exact_values_have_zero_residual():
    aapl = default_registry().get("XNAS:equity:AAPL")
    exact = round_price(aapl, Decimal("227.75"))
    assert exact.is_exact()
    assert (exact.value, exact.residual) == (Decimal("227.75"), Decimal("0"))
