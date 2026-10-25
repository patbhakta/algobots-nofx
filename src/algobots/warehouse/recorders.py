"""Read-only exporters for observer ledgers and the paper-node Redis stream.

Export a bounded read, preserve every source row, and record the source cursor.
No observer or stream is modified; a correction needs a fresh snapshot identity.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pyarrow as pa

from algobots.warehouse import Warehouse, WarehouseError


def export_observer(
    warehouse: Warehouse,
    feed: str,
    source: Path,
    snapshot_id: str,
    *,
    instrument_id: str,
    provider_release: str,
    retrieved_at: float,
) -> dict[str, Any]:
    if feed not in {"kalshi", "pmus"}:
        raise WarehouseError("unknown observer feed")
    rows = [json.loads(line) for line in source.read_text().splitlines() if line.strip()]
    return export_rows(
        warehouse,
        feed,
        rows,
        snapshot_id,
        instrument_id=instrument_id,
        provider_release=provider_release,
        retrieved_at=retrieved_at,
        query={"source": str(source)},
        timestamp_column="close_ts",
        key_columns=["event"],
    )


def export_paper_stream(
    warehouse: Warehouse,
    client: Any,
    snapshot_id: str,
    *,
    instrument_id: str,
    provider_release: str,
    retrieved_at: float,
    start: str = "-",
    end: str = "+",
) -> dict[str, Any]:
    source = "algobots:feed:nautilus-paper"
    messages = client.xrange(source, min=start, max=end)

    def decode(value):
        return value.decode() if isinstance(value, bytes) else str(value)

    rows = []
    for cursor, fields in messages:
        row = {decode(k): decode(v) for k, v in fields.items()}
        if row["instrument"] != instrument_id:
            raise WarehouseError("paper stream instrument mismatch")
        row["stream_id"] = decode(cursor)
        row["timestamp"] = int(row["node_ts"]) / 1_000_000_000
        rows.append(row)
    return export_rows(
        warehouse,
        "nautilus-paper",
        rows,
        snapshot_id,
        instrument_id=instrument_id,
        provider_release=provider_release,
        retrieved_at=retrieved_at,
        query={
            "stream": source,
            "start": start,
            "end": end,
            "last_id": rows[-1]["stream_id"] if rows else None,
        },
        timestamp_column="timestamp",
        key_columns=["stream_id"],
    )


def export_rows(
    warehouse: Warehouse,
    feed: str,
    rows: list[dict],
    snapshot_id: str,
    *,
    instrument_id: str,
    provider_release: str,
    retrieved_at: float,
    query: dict,
    timestamp_column: str,
    key_columns: list[str],
) -> dict[str, Any]:
    if not rows:
        raise WarehouseError("no recorder rows to export")
    # Explicit union schema avoids dropping keys absent in the first observation.
    keys = sorted({key for row in rows for key in row})
    table = pa.table({key: [row.get(key) for row in rows] for key in keys})
    return warehouse.publish(
        snapshot_id,
        table,
        instrument_id=instrument_id,
        provider=feed,
        timestamp_column=timestamp_column,
        key_columns=key_columns,
        expected_interval=None,
        metadata={
            "dataset": feed,
            "provider_release": provider_release,
            "query": query,
            "instrument_mapping": {feed: instrument_id},
            "retrieval_start": retrieved_at,
            "retrieval_end": retrieved_at,
            "timezone": "UTC",
            "units": "source-native",
            "precision": "source-native",
            "adjustment_policy": "none",
            "schema_version": 1,
            "gap_policy": "irregular-recorded-events",
        },
    )


def export_observer_quotes(
    warehouse: Warehouse,
    snapshot_id: str,
    catalog_root: Path,
) -> Path:
    """Catalog the observer's recorded YES book with a real expiring instrument.

    Rows without a book remain in the ledger but do not invent quotes. Sizes
    were not recorded: zero sizes make this a price record, not fill liquidity.
    """
    from decimal import Decimal

    from nautilus_trader.model.currencies import USD
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.enums import AssetClass
    from nautilus_trader.model.identifiers import InstrumentId, Symbol, Venue
    from nautilus_trader.model.instruments import BinaryOption
    from nautilus_trader.model.objects import Price, Quantity

    from algobots.warehouse.catalog import publish_quotes

    manifest, table = warehouse.load(snapshot_id)
    venue = Venue("KALSHI" if manifest["provider"] == "kalshi" else "PMUS")
    instruments, quotes = {}, []
    for row in table.to_pylist():
        bid, ask = row.get("mkt_yes_bid"), row.get("mkt_yes_ask")
        if bid is None or ask is None:
            continue
        bid_px, ask_px = Decimal(str(bid)), Decimal(str(ask))
        precision = max(2, -bid_px.as_tuple().exponent, -ask_px.as_tuple().exponent)
        symbol = Symbol(f"{row['event']}-YES")
        expiry = int(Decimal(str(row["close_ts"])) * 1_000_000_000)
        ts = int(Decimal(str(row["ts"])) * 1_000_000_000)
        inst = BinaryOption(
            instrument_id=InstrumentId(symbol, venue),
            raw_symbol=symbol,
            asset_class=AssetClass.CRYPTOCURRENCY,
            currency=USD,
            price_precision=precision,
            size_precision=0,
            price_increment=Price.from_str(f"{Decimal(10) ** -precision:.{precision}f}"),
            size_increment=Quantity.from_int(1),
            activation_ns=expiry - 900_000_000_000,
            expiration_ns=expiry,
            ts_event=ts,
            ts_init=ts,
            outcome="YES",
        )
        instruments[inst.id] = inst
        quotes.append(
            QuoteTick(
                inst.id,
                Price.from_str(f"{bid_px:.{precision}f}"),
                Price.from_str(f"{ask_px:.{precision}f}"),
                Quantity.from_int(0),
                Quantity.from_int(0),
                ts,
                ts,
            )
        )
    quotes.sort(key=lambda quote: quote.ts_init)
    return publish_quotes(snapshot_id, list(instruments.values()), quotes, catalog_root)


def export_paper_quotes(warehouse: Warehouse, snapshot_id: str, catalog_root: Path) -> Path:
    """Catalog paper-node quotes at node time, retaining recorded time in the ledger."""
    from decimal import Decimal

    from nautilus_trader.model.currencies import Currency
    from nautilus_trader.model.data import QuoteTick
    from nautilus_trader.model.identifiers import InstrumentId, Symbol
    from nautilus_trader.model.instruments import CurrencyPair
    from nautilus_trader.model.objects import Price, Quantity

    from algobots.warehouse.catalog import publish_quotes

    manifest, table = warehouse.load(snapshot_id)
    identity = InstrumentId.from_str(manifest["instrument_id"])
    symbol = identity.symbol.value
    if "/" in symbol:
        base, quote = symbol.split("/")
    elif symbol == "EURUSD":
        base, quote = "EUR", "USD"
    else:
        raise WarehouseError("paper quote instrument needs explicit base/quote mapping")
    rows = table.to_pylist()
    precision = max(
        max(-Decimal(row[key]).as_tuple().exponent, 0) for row in rows for key in ("bid", "ask")
    )
    inst = CurrencyPair(
        instrument_id=identity,
        raw_symbol=Symbol(symbol),
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=precision,
        size_precision=0,
        price_increment=Price.from_str(f"{Decimal(10) ** -precision:.{precision}f}"),
        size_increment=Quantity.from_int(1),
        ts_event=0,
        ts_init=0,
    )
    quotes = [
        QuoteTick(
            identity,
            Price.from_str(f"{Decimal(row['bid']):.{precision}f}"),
            Price.from_str(f"{Decimal(row['ask']):.{precision}f}"),
            Quantity.from_int(0),
            Quantity.from_int(0),
            int(row["node_ts"]),
            int(row["node_ts"]),
        )
        for row in rows
    ]
    return publish_quotes(snapshot_id, [inst], quotes, catalog_root)
