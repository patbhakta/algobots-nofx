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
