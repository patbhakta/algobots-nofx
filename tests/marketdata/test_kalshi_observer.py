"""ALG-3357: the Kalshi observer writes rows the demo ledger, quality lane and workers read."""

from datetime import UTC, datetime

from algobots.demo import ledger as L
from algobots.demo import quality as Q
from algobots.marketdata import kalshi_observer as K

# 2026-10-22 13:00:30Z: 30s into the interval that closes 13:15Z = 09:15 ET
NOW = datetime(2026, 10, 22, 13, 0, 30, tzinfo=UTC).timestamp()
EVENT = "KXBTC15M-26OCT220915"


def market(status="active", result="", bid="0.4800", ask="0.5300"):
    return {
        "ticker": f"{EVENT}-15",
        "status": status,
        "floor_strike": 82441.97,
        "open_time": "2026-10-22T13:00:00Z",
        "close_time": "2026-10-22T13:15:00Z",
        "yes_bid_dollars": bid,
        "yes_ask_dollars": ask,
        "result": result,
        "expiration_value": "82500.10" if result else "",
    }


class FakeKalshi:
    def __init__(self, m):
        self.m, self.calls = m, []

    def __call__(self, url):
        self.calls.append(url)
        if isinstance(self.m, Exception):
            raise self.m
        return {"markets": [self.m] if url.endswith(EVENT) else []}


def test_event_ticker_names_the_close_in_exchange_time():
    assert K.event_for(K.current_close(NOW)) == EVENT


def test_decide_then_settle_feeds_the_ledger(tmp_path):
    feed = tmp_path / "observations.jsonl"
    api = FakeKalshi(market())
    obs = K.Observer(feed, get=api)

    assert obs.poll(NOW)["decided"] == EVENT
    assert obs.poll(NOW + 20)["decided"] is None  # one row per interval
    [row] = obs.read()
    assert row["outcome"] is None and row["p"] == 0.5 and row["p_source"] == "none"
    assert row["mkt_mid"] == 0.505  # evidence only, never the signal
    assert L.load_rows(feed) == []  # pending: the ledger waits for settlement
    [pending] = Q.load_pending(feed)
    assert pending.event == EVENT and pending.strike == 82441.97

    api.m = market(status="finalized", result="yes")
    assert obs.poll(NOW + 600)["settled"] == []  # before close: not asked yet
    assert obs.poll(NOW + 900)["settled"] == [EVENT]
    [r] = L.load_rows(feed)
    assert (r.event, r.outcome, r.ts) == (EVENT, 1, NOW)
    assert Q.load_pending(feed) == []

    books = L.build([r]).books
    assert books["laya"].decisions[0].status == "ABSTAIN"  # neutral p: no fake edge
    assert books["jev"].decisions[0].status == "ABSTAIN"
    assert books["coin"].decisions[0].status == "FILLED"


def test_late_or_closed_intervals_are_not_decided(tmp_path):
    feed = tmp_path / "observations.jsonl"
    assert K.Observer(feed, get=FakeKalshi(market())).poll(NOW + 400)["decided"] is None
    res = K.Observer(feed, get=FakeKalshi(market(status="closed"))).poll(NOW)
    assert res["decided"] is None and "not tradeable" in res["errors"][0]
    assert not feed.exists()


def test_exchange_outage_writes_nothing_and_retries(tmp_path):
    feed = tmp_path / "observations.jsonl"
    obs = K.Observer(feed, get=FakeKalshi(OSError("HTTP Error 503: Service Unavailable")))
    res = obs.poll(NOW)
    assert res["decided"] is None and "503" in res["errors"][0]
    assert not feed.exists()
    obs.get = FakeKalshi(market())
    assert obs.poll(NOW + 20)["decided"] == EVENT


def test_rewrite_keeps_foreign_rows(tmp_path):
    feed = tmp_path / "observations.jsonl"
    old = '{"event": "KXBTC15M-26OCT160900", "strike": 1, "outcome": 0, "ts": 1, "p": 0.3}\n'
    feed.write_text(old)
    K.Observer(feed, get=FakeKalshi(market())).poll(NOW)
    assert feed.read_text().startswith(old.strip()[:-1])  # history kept, new row appended
    assert [r.event for r in L.load_rows(feed)] == ["KXBTC15M-26OCT160900"]
