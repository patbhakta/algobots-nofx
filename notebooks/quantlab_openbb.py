"""Free OpenBB snapshot -> shared manifest -> rc6 catalog -> engine replay.

Run as marimo notebook or: python quantlab_openbb.py --acceptance
"""

import marimo

app = marimo.App()


def publish_snapshot():
    import json
    import os
    import stat
    import uuid
    from datetime import UTC, datetime
    from importlib.metadata import version
    from pathlib import Path

    import pandas as pd
    import pyarrow as pa
    from nautilus_trader.backtest import BacktestEngine
    from nautilus_trader.config import BacktestEngineConfig
    from nautilus_trader.execution import FixedFeeModel
    from nautilus_trader.model import (
        AccountType,
        Bar,
        BarType,
        Currency,
        Equity,
        InstrumentId,
        Money,
        OmsType,
        Price,
        Quantity,
        Symbol,
        Venue,
    )
    from nautilus_trader.persistence import ParquetDataCatalog
    from openbb import obb

    from algobots.warehouse import Warehouse
    from algobots.warehouse.catalog import publish_bars

    os.umask(0o002)
    assert (os.getuid(), os.getgid()) == (1000, 1000), "acceptance requires UID/GID 1000"
    probe = Path("/home/quantlab") / f".acceptance-{uuid.uuid4().hex}"
    try:
        probe.write_text("uid1000 write/read-back\n")
        assert probe.read_text() == "uid1000 write/read-back\n"
        with probe.open("a") as output:
            output.write("group-write verified\n")
        assert probe.read_text().endswith("group-write verified\n")
        info = probe.stat()
        assert info.st_gid == 1000 and info.st_mode & stat.S_IWGRP
        print(
            json.dumps(
                dict(
                    uid=os.getuid(),
                    gid=os.getgid(),
                    write_read_back=True,
                    output_uid=info.st_uid,
                    output_gid=info.st_gid,
                    output_mode=oct(stat.S_IMODE(info.st_mode)),
                )
            )
        )
    finally:
        probe.unlink(missing_ok=True)
    USD = Currency.from_str("USD")

    assert version("nautilus_trader") == "2.0.0rc6"
    started = datetime.now(UTC).isoformat()
    query = dict(symbol="SPY", provider="yfinance", start_date="2026-09-01", end_date="2026-09-15")
    frame = obb.equity.price.historical(**query).to_df().reset_index()
    frame["date"] = pd.to_datetime(frame["date"], utc=True)
    frame = frame.sort_values("date")
    assert len(frame) >= 5 and not frame["date"].duplicated().any()
    snapshot_id = "openbb-spy-" + uuid.uuid4().hex[:16]
    instrument = Equity(
        instrument_id=InstrumentId.from_str("SPY.NYSE"),
        raw_symbol=Symbol("SPY"),
        currency=USD,
        price_precision=2,
        price_increment=Price.from_str("0.01"),
        lot_size=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
    bar_type = BarType.from_str("SPY.NYSE-1-DAY-LAST-EXTERNAL")
    bars = []
    rows = []
    for _, row in frame.iterrows():
        # Daily bars become available at end of the provider's labeled UTC day.
        ns = int(row["date"].value) + 86_400_000_000_000
        prices = [Price.from_str(f"{row[key]:.2f}") for key in ("open", "high", "low", "close")]
        volume = Quantity.from_int(int(row["volume"]))
        bars.append(Bar(bar_type, *prices, volume, ts_event=ns, ts_init=ns))
        rows.append(
            dict(
                timestamp=ns / 1e9,
                open=float(prices[0]),
                high=float(prices[1]),
                low=float(prices[2]),
                close=float(prices[3]),
                volume=int(row["volume"]),
            )
        )
    catalog_root = Path("/home/quantlab/ntl_catalog")
    catalog_path = publish_bars(snapshot_id, instrument, bars, catalog_root)
    replay = ParquetDataCatalog(str(catalog_path)).query_bars()
    engine = BacktestEngine(config=BacktestEngineConfig())
    try:
        engine.add_venue(
            venue=Venue("NYSE"),
            oms_type=OmsType.NETTING,
            account_type=AccountType.CASH,
            base_currency=USD,
            starting_balances=[Money.from_str("100000 USD")],
            fee_model=FixedFeeModel(Money.from_str("0 USD")),
        )
        engine.add_instrument(instrument)
        engine.add_data(replay)
        engine.run()
        processed = engine.iteration
        assert processed == len(bars), (processed, len(bars))
    finally:
        engine.dispose()
    manifest = Warehouse(Path("/home/quantlab/openbb_store")).publish(
        snapshot_id,
        pa.Table.from_pylist(rows),
        instrument_id=str(instrument.id),
        provider="yfinance",
        timestamp_column="timestamp",
        key_columns=["timestamp"],
        expected_interval=None,
        namespace="external",
        metadata=dict(
            dataset="openbb-spy-daily",
            provider_release=version("openbb"),
            query=query,
            instrument_mapping={"SPY": "SPY.NYSE"},
            retrieval_start=started,
            retrieval_end=datetime.now(UTC).isoformat(),
            timezone="UTC",
            units="USD,shares",
            precision={"price": 2, "volume": 0},
            adjustment_policy="provider default; no additional adjustment",
            schema_version="1",
            gap_policy="irregular-recorded-events",
            timestamp_policy=(
                "provider UTC date plus one day; conservative daily close availability"
            ),
            catalog_path=snapshot_id,
            catalog_data_class="Bar",
            nautilus_version=version("nautilus_trader"),
            engine_events=processed,
        ),
    )
    loaded, table = Warehouse(Path("/home/quantlab/openbb_store")).load(snapshot_id)
    assert loaded == manifest and table.num_rows == len(rows)
    print(
        json.dumps(
            dict(
                snapshot_id=snapshot_id,
                rows=len(rows),
                engine_events=processed,
                catalog_path=str(catalog_path),
                manifest=manifest,
            ),
            sort_keys=True,
        )
    )
    return manifest


@app.cell
def _():
    import marimo as mo

    mo.md(
        "# OpenBB warehouse acceptance\n"
        "Free yfinance daily bars, immutable shared manifest, rc6 catalog API and engine replay."
    )
    return


@app.cell
def _():
    from quantlab_openbb import publish_snapshot

    manifest = publish_snapshot()
    print(manifest)
    return


if __name__ == "__main__":
    import sys

    if "--acceptance" in sys.argv:
        publish_snapshot()
    else:
        app.run()
