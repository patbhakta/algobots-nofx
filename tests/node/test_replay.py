"""ALG-3406: the replay feed's engine-free pieces — catalog decode, pacing, feed signal."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from algobots.node import replay


def _fixed(value: float) -> bytes:
    return int(round(value * replay.FIXED_SCALAR)).to_bytes(16, "little", signed=True)


def _catalog(path, rows):
    """A quote_tick file shaped like the Nautech image's /catalog (rc6 layout)."""
    fsb = pa.binary(16)
    table = pa.table(
        {
            "bid_price": pa.array([_fixed(b) for b, _, _ in rows], fsb),
            "ask_price": pa.array([_fixed(a) for _, a, _ in rows], fsb),
            "bid_size": pa.array([_fixed(1_000_000)] * len(rows), fsb),
            "ask_size": pa.array([_fixed(1_000_000)] * len(rows), fsb),
            "ts_event": pa.array([t for _, _, t in rows], pa.uint64()),
            "ts_init": pa.array([t for _, _, t in rows], pa.uint64()),
        }
    ).replace_schema_metadata(
        {"instrument_id": "EUR/USD.SIM", "price_precision": "5", "size_precision": "0"}
    )
    pq.write_table(table, path, row_group_size=2)
    return str(path)


def test_raw_decodes_the_bytes_captured_off_the_243_catalog():
    # First row of /catalog/data/quote_tick/EURUSD.SIM/part-0.parquet in the node image.
    bid = b"\x00\xc08-A\xd5'\x00\x00\x00\x00\x00\x00\x00\x00\x00"
    size = b"\x00\x00@\xb2\xba\xc9\xe0\x19\x1e\x02\x00\x00\x00\x00\x00\x00"
    assert replay.raw(bid) == 11_212_000_000_000_000  # 1.12120
    assert replay.raw(size) == 1_000_000 * replay.FIXED_SCALAR


def test_read_quotes_streams_every_row_in_order_across_row_groups(tmp_path):
    t0 = 1_577_898_010_447_000_000
    rows = [
        (1.1212, 1.1214, t0),
        (1.1213, 1.1215, t0 + 51_000_000),
        (1.1211, 1.1213, t0 + 2 * 10**9),
    ]
    path = _catalog(tmp_path / "part-0.parquet", rows)
    quotes = list(replay.read_quotes(path, batch_rows=1))
    assert [q.row for q in quotes] == [0, 1, 2]
    assert [q.ts_event for q in quotes] == [t for _, _, t in rows]
    assert [(round(q.bid, 5), round(q.ask, 5)) for q in quotes] == [(b, a) for b, a, _ in rows]
    assert replay.catalog_meta(path)["instrument_id"] == "EUR/USD.SIM"


def test_pace_replays_recorded_gaps_scaled_and_capped():
    s = 10**9
    assert replay.pace(None, 5 * s, 1.0, 2.0) == 0.0
    assert replay.pace(5 * s, 5 * s, 1.0, 2.0) == 0.0  # same-timestamp quotes: no wait
    assert replay.pace(0, s // 2, 1.0, 2.0) == 0.5
    assert replay.pace(0, s, 4.0, 2.0) == 0.25
    assert replay.pace(0, 3600 * s, 1.0, 2.0) == 2.0  # a weekend never stalls the feed


class _Redis:
    def __init__(self):
        self.entries = []

    def xadd(self, key, fields, maxlen=None, approximate=False):
        self.entries.append((key, fields, maxlen, approximate))


def test_feed_signal_writes_what_the_node_received_at_most_once_per_interval():
    r = _Redis()
    sig = replay.FeedSignal(client=r, node="nautilus-paper", every_s=1.0)
    cur = replay.ReplayCursor(source="replay:/catalog/x.parquet", instrument="EUR/USD.SIM")
    cur.row, cur.recorded_ts = 7, 1_577_898_010_447_000_000
    s = 10**9
    wrote = [
        sig.on_quote(ts_init=t, bid="1.12120", ask="1.12140", cursor=cur)
        for t in (100 * s, 100 * s + s // 2, 101 * s)
    ]
    assert wrote == [True, False, True]
    assert (sig.received, sig.written) == (3, 2)
    key, fields, maxlen, approx = r.entries[-1]
    assert key == "algobots:feed:nautilus-paper" == replay.feed_key("nautilus-paper")
    assert fields["source"] == "replay:/catalog/x.parquet"
    assert fields["recorded_ts"] == str(cur.recorded_ts)
    assert fields["node_ts"] == str(101 * s)
    assert fields["received"] == "3"
    assert approx and maxlen == sig.maxlen


def test_a_feed_without_a_replay_cursor_is_labelled_synthetic():
    r = _Redis()
    replay.FeedSignal(client=r, node="n").on_quote(ts_init=1, bid="1", ask="1", cursor=None)
    assert r.entries[0][1]["source"] == replay.SYNTHETIC
