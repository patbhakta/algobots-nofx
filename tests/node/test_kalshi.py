"""ALG-3411: the live Kalshi feed's engine-free pieces — parse, tail, settings, instrument."""

from __future__ import annotations

import json
from decimal import Decimal

from algobots.node import kalshi
from algobots.node import paper_node


def _obs(ts=1792899916.9, bid=0.51, ask=0.52, market="KXBTC15M-26OCT250000-00"):
    return json.dumps(
        {
            "event": "KXBTC15M-26OCT250000",
            "market": market,
            "ts": ts,
            "mkt_yes_bid": bid,
            "mkt_yes_ask": ask,
            "mkt_mid": (bid + ask) / 2,
        }
    )


def test_parse_line_reads_the_observers_book(tmp_path):
    obs = kalshi.parse_line(3, _obs())
    assert obs is not None
    assert obs.row == 3
    assert obs.market == "KXBTC15M-26OCT250000-00"
    assert obs.bid == Decimal("0.51")
    assert obs.ask == Decimal("0.52")
    assert obs.ts_ns == 1_792_899_916_900_000_000  # wall clock, nanoseconds


def test_parse_line_drops_lines_without_a_book():
    pre_open = json.dumps({"market": "KXBTC15M-X", "ts": 1.0, "mkt_yes_bid": None, "mkt_yes_ask": None})
    assert kalshi.parse_line(1, pre_open) is None


def test_parse_line_survives_a_torn_tail_write():
    assert kalshi.parse_line(1, '{"market": "KXBTC15M-X", "ts": 1.0, "mkt_yes') is None


def test_tail_bootstraps_the_last_book_and_follows_appends(tmp_path):
    f = tmp_path / "observations.jsonl"
    f.write_text(_obs(ts=1.0, bid=0.40, ask=0.41) + "\n" + _obs(ts=2.0, bid=0.50, ask=0.51) + "\n")
    tail = kalshi.ObservationTail(str(f))
    latest = tail.bootstrap()
    assert latest is not None and (latest.bid, latest.ask, latest.row) == (Decimal("0.50"), Decimal("0.51"), 2)

    with f.open("a") as h:  # a new 15-minute boundary lands
        h.write(_obs(ts=900.0, bid=0.60, ask=0.61, market="KXBTC15M-NEXT-00") + "\n")
    nxt = tail.poll()
    assert nxt is not None and (nxt.bid, nxt.row) == (Decimal("0.60"), 3)
    assert tail.poll() is None  # one line per poll, nothing new after


def test_tail_holds_back_a_partial_line_until_it_completes(tmp_path):
    f = tmp_path / "observations.jsonl"
    f.write_text(_obs(ts=1.0) + "\n")
    tail = kalshi.ObservationTail(str(f))
    assert tail.bootstrap() is not None
    with f.open("a") as h:
        h.write('{"market": "KXBTC15M-X", "ts": 2.0, "mkt_yes')  # torn write
    assert tail.poll() is None  # not a line yet; the book stands
    with f.open("a") as h:
        h.write('_bid": 0.70, "mkt_yes_ask": 0.71}\n')  # the observer finishes it
    done = tail.poll()
    assert done is not None and done.bid == Decimal("0.70")


def test_settings_read_the_kalshi_environment():
    s = paper_node.settings(
        {
            "ALGOBOTS_FEED": "kalshi",
            "ALGOBOTS_NODE_SYMBOL": "KXBTC15M/USD.SIM",
            "ALGOBOTS_KALSHI_PATH": "/feeds/kalshi/observations.jsonl",
            "ALGOBOTS_KALSHI_POLL_S": "3",
        }
    )
    assert s.feed == "kalshi"
    assert s.symbol == "KXBTC15M/USD.SIM"
    assert s.kalshi_path == "/feeds/kalshi/observations.jsonl"
    assert s.kalshi_poll_s == 3.0
    assert paper_node.settings({}).kalshi_path == kalshi.DEFAULT_PATH


def test_kalshi_instrument_is_a_cents_contract():
    s = paper_node.settings({"ALGOBOTS_FEED": "kalshi", "ALGOBOTS_NODE_SYMBOL": "KXBTC15M/USD.SIM"})
    inst = paper_node._instrument(s)
    assert str(inst.id) == "KXBTC15M/USD.SIM"
    assert inst.price_precision == 2
    assert inst.size_precision == 0
    assert str(inst.price_increment) == "0.01"
    assert str(inst.size_increment) == "1"
