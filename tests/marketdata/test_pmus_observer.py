"""ALG-3411: the Polymarket US observer (stdlib only, loaded by file path like the PM test)."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "algobots" / "marketdata" / "pmus_observer.py"
spec = importlib.util.spec_from_file_location("pmus", SRC)
U = importlib.util.module_from_spec(spec)
spec.loader.exec_module(U)

# 2026-10-23 08:15:30Z: 30s into the 08:15-08:30Z interval (shapes captured live)
NOW = datetime(2026, 10, 23, 8, 15, 30, tzinfo=UTC).timestamp()
EVENT = "btc-updown-15m-2026-10-23-0815z"
MKT = "cpc-" + EVENT


def market(status="MARKET_STATUS_OPEN", ptb="81641.70", settle=None):
    return {
        "slug": MKT,
        "status": status,
        "assetPriceTerms": {
            "indexSymbol": "BRTI",
            "windowStart": "2026-10-23T08:15:00Z",
            "windowEnd": "2026-10-23T08:30:00Z",
            "priceToBeat": {"value": ptb, "currency": "USD"} if ptb else None,
            "settlementPrice": {"value": settle, "currency": "USD"} if settle else None,
        },
    }


BBO = {"marketData": {
    "marketSlug": MKT,
    "bestBid": {"value": "0.8300", "currency": "USD"},
    "bestAsk": {"value": "0.8400", "currency": "USD"},
    "sharesTraded": "61143.6300",
    "openInterest": "16387.7700",
}}


class FakeGateway:
    def __init__(self, m, bbo=BBO, settlement=None):
        self.m, self.bbo, self.settlement, self.calls = m, bbo, settlement, []

    def __call__(self, url):
        self.calls.append(url)
        if url.endswith(f"/v1/events?slug={EVENT}"):
            return {"events": [{"slug": EVENT, "markets": [self.m]}]}
        if url.endswith(f"/v1/markets/{MKT}/bbo"):
            return self.bbo
        if url.endswith(f"/v1/markets/{MKT}/settlement"):
            return self.settlement
        return None  # 404


def test_slug_names_the_interval_start_in_utc():
    assert U.slug_for(NOW) == EVENT


def test_decides_with_venue_strike_and_book_evidence(tmp_path):
    feed = tmp_path / "observations.jsonl"
    res = U.Observer(feed, get=FakeGateway(market())).poll(NOW)
    assert res["decided"] == EVENT and not res["errors"]
    (row,) = [json.loads(x) for x in feed.read_text().splitlines()]
    assert row["strike"] == 81641.70 and row["strike_basis"] == "venue-priceToBeat-cf-brti"
    assert row["venue"] == "polymarket-us" and row["market"] == MKT
    assert (row["p"], row["p_source"]) == (0.5, "none")  # book is evidence, never the signal
    assert (row["mkt_yes_bid"], row["mkt_yes_ask"], row["mkt_mid"]) == (0.83, 0.84, 0.835)
    assert row["close_ts"] - row["open_ts"] == 900 and row["outcome"] is None


def test_no_row_without_open_status_or_book(tmp_path):
    feed = tmp_path / "observations.jsonl"
    closed = market(status="MARKET_STATUS_CLOSED", ptb=None)
    res = U.Observer(feed, get=FakeGateway(closed)).poll(NOW)
    assert res["decided"] is None and "not decidable" in res["errors"][0]
    res = U.Observer(feed, get=FakeGateway(market(), bbo=None)).poll(NOW)
    assert res["decided"] is None and "two-sided" in res["errors"][0]
    assert not feed.exists()


def test_no_decide_late_in_the_interval(tmp_path):
    feed = tmp_path / "observations.jsonl"
    gw = FakeGateway(market())
    assert U.Observer(feed, get=gw).poll(NOW + 400)["decided"] is None
    assert gw.calls == []


def test_settles_from_published_binary_and_checks_brti(tmp_path):
    feed = tmp_path / "observations.jsonl"
    U.Observer(feed, get=FakeGateway(market())).poll(NOW)
    after = NOW + 900
    # not published yet (404) -> stays pending
    assert U.Observer(feed, get=FakeGateway(market())).poll(after)["settled"] == []
    resolved = market(status="MARKET_STATUS_RESOLVED", settle="81471.69")
    gw = FakeGateway(resolved, settlement={"settlement": 0})
    assert U.Observer(feed, get=gw).poll(after)["settled"] == [EVENT]
    (row,) = [json.loads(x) for x in feed.read_text().splitlines()]
    assert row["outcome"] == 0 and row["settle_price"] == 81471.69
    assert row["settle_consistent"] is True


def test_flags_a_settlement_that_contradicts_brti(tmp_path):
    feed = tmp_path / "observations.jsonl"
    U.Observer(feed, get=FakeGateway(market())).poll(NOW)
    resolved = market(status="MARKET_STATUS_RESOLVED", settle="81700.00")
    gw = FakeGateway(resolved, settlement={"settlement": 0})
    U.Observer(feed, get=gw).poll(NOW + 900)
    (row,) = [json.loads(x) for x in feed.read_text().splitlines()]
    assert row["settle_consistent"] is False


def test_api_error_is_reported_not_raised(tmp_path):
    def boom(_url):
        raise OSError("gateway down")
    res = U.Observer(tmp_path / "o.jsonl", get=boom).poll(NOW)
    assert res["decided"] is None and "gateway down" in res["errors"][0]
