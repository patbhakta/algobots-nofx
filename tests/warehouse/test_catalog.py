import pytest
from nautilus_trader.model.currencies import BTC, USD
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.identifiers import InstrumentId, Symbol
from nautilus_trader.model.instruments import CurrencyPair
from nautilus_trader.model.objects import Price, Quantity
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from algobots.warehouse import WarehouseError
from algobots.warehouse.catalog import publish_bars


def test_five_bar_nautilus_consumption_and_immutable_catalog(tmp_path):
    inst = CurrencyPair(
        instrument_id=InstrumentId.from_str("BTCUSD.PAPER"),
        raw_symbol=Symbol("BTCUSD"),
        base_currency=BTC,
        quote_currency=USD,
        price_precision=2,
        size_precision=0,
        price_increment=Price.from_str("0.01"),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
    kind = BarType.from_str("BTCUSD.PAPER-1-MINUTE-LAST-EXTERNAL")
    px = Price.from_str("100.00")
    bars = [
        Bar(kind, px, px, px, px, Quantity.from_int(1), i * 60_000_000_000, i * 60_000_000_000)
        for i in range(1, 6)
    ]
    path = publish_bars("five-bars", inst, bars, tmp_path)
    catalog = ParquetDataCatalog(str(path))
    assert catalog.query(Bar) == bars
    assert catalog.instruments()[0].id == inst.id
    assert catalog.query(Bar)[-1].ts_event == 300_000_000_000
    with pytest.raises(WarehouseError, match="already published"):
        publish_bars("five-bars", inst, bars[:1], tmp_path)
    assert catalog.query(Bar) == bars
