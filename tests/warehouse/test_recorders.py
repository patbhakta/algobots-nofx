import json

import pytest

from algobots.warehouse import Warehouse
from algobots.warehouse.recorders import export_observer, export_paper_stream


@pytest.mark.parametrize("feed", ["kalshi", "pmus"])
def test_observer_preserves_source_count_and_optional_fields(tmp_path, feed):
    source = tmp_path / "observations.jsonl"
    rows = [
        dict(event="a", close_ts=900, outcome=1),
        dict(event="b", close_ts=2700, outcome=None, mkt_yes_ask=0.52),
    ]
    source.write_text("\n".join(json.dumps(row) for row in rows))
    before = source.read_bytes()
    warehouse = Warehouse(tmp_path / "warehouse")
    manifest = export_observer(
        warehouse,
        feed,
        source,
        "snapshot",
        instrument_id="KXBTC15M.KALSHI",
        provider_release="fixture",
        retrieved_at=3000,
    )
    assert manifest["row_count"] == len(rows)
    assert manifest["path"].startswith(f"ledger/{feed}/v1/date=1970-01-01/")
    assert (warehouse.root / f"manifests/ledger/{feed}/snapshot.json").exists()
    assert warehouse.load("snapshot")[1].to_pylist()[1]["mkt_yes_ask"] == 0.52
    assert source.read_bytes() == before


def test_paper_stream_records_bounded_cursor_without_mutating_stream(tmp_path):
    class Client:
        def xrange(self, stream, *, min, max):
            assert (stream, min, max) == ("algobots:feed:nautilus-paper", "1-0", "2-0")
            return [
                (
                    b"1-0",
                    {
                        b"instrument": b"EURUSD.SIM",
                        b"node_ts": b"1000000000",
                        b"recorded_ts": b"123",
                        b"bid": b"1.10",
                        b"ask": b"1.11",
                    },
                )
            ]

    warehouse = Warehouse(tmp_path)
    manifest = export_paper_stream(
        warehouse,
        Client(),
        "paper",
        instrument_id="EURUSD.SIM",
        provider_release="fixture",
        retrieved_at=3,
        start="1-0",
        end="2-0",
    )
    assert manifest["row_count"] == 1
    assert manifest["query"]["last_id"] == "1-0"
    assert warehouse.load("paper")[1].to_pylist()[0]["recorded_ts"] == "123"


def test_observer_catalog_query_preserves_recorded_price_precision(tmp_path):
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

    from algobots.warehouse.recorders import export_observer_quotes, export_rows

    warehouse = Warehouse(tmp_path / "warehouse")
    export_rows(
        warehouse,
        "pmus",
        [dict(event="event", close_ts=1800, ts=950, mkt_yes_bid=0.5371, mkt_yes_ask=0.5382)],
        "quotes",
        instrument_id="BTC15M.PMUS",
        provider_release="fixture",
        retrieved_at=2000,
        query={},
        timestamp_column="close_ts",
        key_columns=["event"],
    )
    path = export_observer_quotes(warehouse, "quotes", tmp_path / "catalog")
    quote = ParquetDataCatalog(str(path)).query(QuoteTick)[0]
    assert str(quote.bid_price) == "0.5371"
    assert str(quote.ask_price) == "0.5382"
    assert quote.ts_event == 950_000_000_000
