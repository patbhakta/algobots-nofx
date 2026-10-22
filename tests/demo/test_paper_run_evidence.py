"""Pins the ALG-3403 evidence notebook's parsing against rc6 stream payloads."""

from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

pytest.importorskip("marimo")

NB = Path(__file__).resolve().parents[2] / "notebooks" / "paper_run_evidence.py"
spec = importlib.util.spec_from_file_location("paper_run_evidence", NB)
nb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nb)


def _fill(side: str, qty: str, px: str, ts: int, oid: str) -> dict:
    payload = {
        "Filled": {
            "type": "OrderFilled",
            "strategy_id": "CommandNode-000",
            "instrument_id": "EUR/USD.SIM",
            "client_order_id": oid,
            "trade_id": f"T-{oid}",
            "order_side": side,
            "last_qty": qty,
            "last_px": px,
            "commission": "0.50 USD",
            "position_id": "EUR/USD.SIM-CommandNode-000",
            "ts_event": ts,
        }
    }
    return {"stream_id": f"{ts // 1_000_000}-0", "topic": "", "type": "", "payload": payload}


def test_marker_present():
    assert nb.EVIDENCE_MARKER in NB.read_text()


def test_fills_parse_and_sort():
    events = [
        _fill("SELL", "1000", "1.10200", 1792651030000000000, "b"),
        _fill("BUY", "1000", "1.10000", 1792651022795865352, "a"),
    ]
    rows = nb.fills_table(events)
    assert [r["client_order_id"] for r in rows] == ["a", "b"]
    assert rows[0]["ts_event"] == "2026-10-22T06:37:02.795+00:00"
    assert rows[0]["px"] == Decimal("1.10000")


def test_pnl_round_trip_and_open_remainder():
    fills = nb.fills_table(
        [
            _fill("BUY", "2000", "1.10000", 1, "a"),
            _fill("SELL", "1000", "1.10200", 2, "b"),
        ]
    )
    (row,) = nb.pnl_from_fills(fills)
    assert row["net_qty"] == Decimal(1000)
    assert row["realized"] == Decimal("2.00000")
    assert row["unrealized"] == Decimal("2.00000")
    assert row["commission"] == Decimal("1.00")
    assert row["net_pnl"] == Decimal("3.00000")


def test_pnl_flip_resets_average():
    fills = nb.fills_table(
        [_fill("BUY", "1000", "1.0", 1, "a"), _fill("SELL", "3000", "1.1", 2, "b")]
    )
    (row,) = nb.pnl_from_fills(fills)
    assert row["net_qty"] == Decimal(-2000)
    assert row["avg_px"] == Decimal("1.1")
    assert row["realized"] == Decimal("100.0")


def test_timestamps_handle_ns_and_iso_events():
    hb = {"type": "AlgoBotsHeartbeat", "ts_event": "2026-10-22T06:39:34.594Z"}
    streams = {
        "trader-X:algobots:events.heartbeat.n": [
            {"stream_id": "1792651174595-0", "payload": hb},
        ],
        "trader-X:algobots:events.order_filled.EUR/USD.SIM": [
            _fill("BUY", "1000", "1.1", 1792651022795865352, "a")
        ],
    }
    rows = {r["stream"]: r for r in nb.timestamp_table(streams)}
    assert rows["events.heartbeat.n"]["last_ts_event"] == hb["ts_event"]
    assert rows["events.heartbeat.n"]["last_published"].startswith("2026-10-22T06:39:34.595")
    assert rows["events.order_filled.EUR/USD.SIM"]["first_ts_event"].startswith("2026-10-22T06:37")


def test_unwrap_leaves_flat_payloads():
    flat = {"account_id": "SIM-001", "balances": []}
    assert nb.unwrap(flat) is flat
    assert nb.unwrap(json.loads('{"PositionOpened": {"side": "LONG"}}')) == {"side": "LONG"}
