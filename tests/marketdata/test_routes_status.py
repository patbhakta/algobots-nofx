"""/instruments and /market-data/status output contracts (A05), plus the
mixed-asset-class watchlist surface with market status, data timestamps and
precision (the A05 demo shape)."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from algobots.marketdata import ReplayFeed, load_recording, watchlist_status
from algobots.marketdata.routes import instruments_router, marketdata_router

SATURDAY = datetime(2026, 10, 31, 15, 0, 30, tzinfo=UTC)


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(instruments_router)
    app.include_router(marketdata_router)
    return TestClient(app)


def test_instruments_route_lists_the_canonical_registry():
    response = _client().get("/instruments")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 5
    ids = {i["instrument_id"] for i in body["instruments"]}
    assert {
        "COINBASE:spot-crypto:BTC-USD",
        "KRAKEN:spot-crypto:BTC-USD",
        "BYBIT:perpetual-swap:BTC-PERP",
        "XNAS:equity:AAPL",
        "XNYS:etf:SPY",
    } <= ids


def test_instrument_route_resolves_and_404s():
    client = _client()
    ok = client.get("/instruments/XNAS:equity:AAPL")
    assert ok.status_code == 200
    assert ok.json()["venue"] == "XNAS"
    assert ok.json()["price_increment"] == "0.01"
    missing = client.get("/instruments/COINBASE:spot-crypto:ETH-USD")
    assert missing.status_code == 404


def test_status_route_two_asset_classes_one_watchlist():
    client = _client()
    response = client.get(
        "/market-data/status",
        params={
            "ids": "XNAS:equity:AAPL,COINBASE:spot-crypto:BTC-USD",
            "as_of": SATURDAY.isoformat(),
        },
    )
    assert response.status_code == 200
    rows = {row["instrument_id"]: row for row in response.json()["statuses"]}
    aapl, btc = rows["XNAS:equity:AAPL"], rows["COINBASE:spot-crypto:BTC-USD"]
    # Market status: equity closed on Saturday, crypto open 24x7.
    assert aapl["market_open"] is False and "weekend" in aapl["market_reason"]
    assert btc["market_open"] is True and btc["market_reason"] == "continuous-24x7"
    # Data timestamps: every field populated from the recorded snapshot.
    assert aapl["last_event_time"] == "2026-10-31T15:00:00+00:00"
    assert aapl["last_available_time"] == "2026-10-31T15:00:01+00:00"
    assert btc["source"] == "coinbase-ws"
    # Precision comes from each instrument's tick/lot metadata.
    assert aapl["price_precision"] == 2 and aapl["quantity_precision"] == 0
    assert btc["price_precision"] == 2 and btc["quantity_precision"] == 8
    # By Saturday 15:00 the 10:30-published correction is long available: the
    # decision quote is the corrected print (seq 6), not the stale seq 5.
    assert btc["sequence"] == 6


def test_status_route_default_as_of_is_deterministic():
    body = _client().get("/market-data/status").json()
    assert body["count"] == 5  # whole registry
    # Default as-of = recording's latest available time: no wall clock leaks in.
    rows = {row["instrument_id"]: row for row in body["statuses"]}
    assert rows["BYBIT:perpetual-swap:BTC-PERP"]["last_event_time"] is not None


def test_status_route_rejects_unknown_ids():
    response = _client().get("/market-data/status", params={"ids": "NOPE:equity:NOPE"})
    assert response.status_code == 404


def test_watchlist_status_reports_freshness_and_eligibility_reasons():
    rows = watchlist_status(
        instrument_ids=("XNAS:equity:AAPL", "COINBASE:spot-crypto:BTC-USD"),
        feed=ReplayFeed(load_recording()),
        as_of=SATURDAY,
    )
    by_id = {row["instrument_id"]: row for row in rows}
    assert by_id["XNAS:equity:AAPL"]["eligible"] is False
    assert any(r.startswith("market-closed") for r in by_id["XNAS:equity:AAPL"]["reasons"])
    # BTC at 15:00:30 Saturday: market open but the 10:04 print is hours old.
    assert by_id["COINBASE:spot-crypto:BTC-USD"]["market_open"] is True
    assert by_id["COINBASE:spot-crypto:BTC-USD"]["fresh"] is False
