"""A05 acceptance case 1: identities are distinct executable IDs.

BTC/USD spot at two venues and a BTC perpetual are three distinct executable
IDs; research symbols stay separate from identities; the perpetual is
identity-only (execution entitlement fails closed by construction).
"""

from __future__ import annotations

import pytest

from algobots.contracts.enums import ProductClass
from algobots.instruments import (
    UnknownInstrumentError,
    UnknownResearchSymbolError,
    default_directory,
    default_registry,
    product_entitled,
)

BTC_SPOT_COINBASE = "COINBASE:spot-crypto:BTC-USD"
BTC_SPOT_KRAKEN = "KRAKEN:spot-crypto:BTC-USD"
BTC_PERP_BYBIT = "BYBIT:perpetual-swap:BTC-PERP"


def test_btc_spot_two_venues_and_perp_are_distinct_executable_ids():
    registry = default_registry()
    ids = {BTC_SPOT_COINBASE, BTC_SPOT_KRAKEN, BTC_PERP_BYBIT}
    assert len(ids) == 3
    for executable_id in ids:
        assert executable_id in registry
        assert registry.get(executable_id).instrument_id == executable_id
    # Same symbol, different venue/product: never aliased onto one ID.
    assert registry.get(BTC_SPOT_COINBASE) is not registry.get(BTC_SPOT_KRAKEN)
    assert registry.get(BTC_SPOT_COINBASE) is not registry.get(BTC_PERP_BYBIT)


def test_identity_triple_roundtrips_and_rejects_unknown():
    registry = default_registry()
    for executable_id in (BTC_SPOT_COINBASE, BTC_SPOT_KRAKEN, BTC_PERP_BYBIT):
        inst = registry.get(executable_id)
        assert registry.resolve(inst.venue, str(inst.product), inst.symbol) is inst
    with pytest.raises(UnknownInstrumentError):
        registry.get("COINBASE:spot-crypto:ETH-USD")
    with pytest.raises(UnknownInstrumentError):
        registry.resolve("COINBASE", "spot-crypto", "BTC-USDT")


def test_registry_rejects_duplicate_identity_or_triple():
    from algobots.contracts import Instrument
    from algobots.instruments.registry import InstrumentRegistry, InstrumentRegistryError

    base = default_registry().get(BTC_SPOT_COINBASE).model_dump()
    twin = Instrument.model_validate(base)
    with pytest.raises(InstrumentRegistryError, match="duplicate instrument_id"):
        InstrumentRegistry((twin, twin))
    # A hand-built record whose ID disagrees with its triple (only possible by
    # bypassing validation) still cannot smuggle a second identity in.
    rogue = Instrument.model_construct(**{**base, "instrument_id": "ROGUE:spot-crypto:BTC-USD"})
    with pytest.raises(InstrumentRegistryError, match="duplicate \\(venue, product, symbol\\)"):
        InstrumentRegistry((twin, rogue))


def test_research_symbols_normalize_separately_from_executable_ids():
    directory = default_directory()
    # Aliases collapse to one research key; the key is not an identity.
    assert directory.executable_ids("BTC/usd") == (BTC_SPOT_COINBASE, BTC_SPOT_KRAKEN)
    assert directory.executable_ids("btc-usd") == (BTC_SPOT_COINBASE, BTC_SPOT_KRAKEN)
    assert directory.executable_ids("BTCUSD") == (BTC_SPOT_COINBASE, BTC_SPOT_KRAKEN)
    assert directory.executable_ids("BTC-PERP") == (BTC_PERP_BYBIT,)
    assert directory.executable_ids("AAPL") == ("XNAS:equity:AAPL",)
    with pytest.raises(UnknownResearchSymbolError):
        directory.executable_ids("DOGE-USD")
    with pytest.raises(ValueError, match="not identities"):
        directory.executable_ids(BTC_SPOT_COINBASE)


def test_entitlements_flow_through_a04_product_permissions():
    registry = default_registry()
    equity_only = (ProductClass.EQUITY,)
    crypto_and_equity = (ProductClass.EQUITY, ProductClass.ETF, ProductClass.SPOT_CRYPTO)

    aapl = registry.get("XNAS:equity:AAPL")
    assert product_entitled(equity_only, aapl).allowed
    assert not product_entitled((ProductClass.SPOT_CRYPTO,), aapl).allowed

    btc = registry.get(BTC_SPOT_COINBASE)
    assert not product_entitled(equity_only, btc).allowed
    assert product_entitled(crypto_and_equity, btc).allowed


def test_perpetual_swap_is_identity_only_and_fails_closed():
    registry = default_registry()
    perp = registry.get(BTC_PERP_BYBIT)
    # Not a ProductClass member: no A04 permission set can ever contain it.
    assert not isinstance(perp.product, ProductClass)
    every_product = tuple(ProductClass)
    verdict = product_entitled(every_product, perp)
    assert not verdict.allowed
    assert verdict.reason == "identity-only-product:perpetual-swap"
