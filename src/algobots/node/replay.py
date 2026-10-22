"""Recorded market data, replayed into the rc6 paper node on a clock (ALG-3406).

DEMO hop 4 needs prices that are *market data*, not the random walk
:mod:`algobots.node.paper_node` started with, and IBKR paper data waits on a
login (ALG-3357). The node image already ships a Nautilus Parquet catalog —
Nautech's base image carries ``/catalog/data/quote_tick/EURUSD.SIM`` (1.64 M
recorded EUR/USD quotes, January 2020) — and EUR/USD.SIM is the node's own
instrument, so that slice is what gets replayed.

The pieces here do not need the engine, so they are tested everywhere:

* :func:`read_quotes` streams the catalog file row group by row group. Nautilus
  stores prices and sizes as 16-byte little-endian fixed-point integers
  (scale ``10**16``); :func:`raw` decodes them, and the node builds
  ``Price.from_raw`` from the result, so no value passes through a float.
* :func:`pace` turns the recorded inter-arrival gap into a sleep: real time at
  ``speed=1``, capped so a weekend or an overnight gap never stalls the feed.
* :class:`FeedSignal` is what the node writes **after** a quote reached its
  strategy: one entry on ``algobots:feed:<node>`` per ``every_s``, carrying the
  recorded timestamp, the node's own receive timestamp and the source. The
  full-loop verifier reads this stream (``tests/demo/full_loop.py``), so "data
  reaches the node" is judged on what the node received, not on a file's mtime.

Replayed quotes are stamped with the node's clock (``ts_event = ts_init = now``)
so the sandbox venue matches against them as current prices; the recorded
time travels in the feed signal (``recorded_ts``) and the node log.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

#: Nautilus' high-precision fixed-point scale (``FIXED_PRECISION = 16``).
FIXED_SCALAR = 10**16

#: Inside the ``nautilus-node`` image (Nautech base, pinned by digest).
DEFAULT_PATH = "/catalog/data/quote_tick/EURUSD.SIM/part-0.parquet"

FEED_PREFIX = "algobots:feed:"

#: The source label of the random-walk client; the verifier refuses it.
SYNTHETIC = "synthetic"


def feed_key(node: str) -> str:
    return f"{FEED_PREFIX}{node}"


def raw(value: bytes) -> int:
    """A Nautilus 16-byte fixed-point column value as its raw integer."""
    return int.from_bytes(value, "little", signed=True)


@dataclass(frozen=True)
class RecordedQuote:
    row: int
    ts_event: int  # ns, as recorded
    bid_raw: int
    ask_raw: int
    bid_size_raw: int
    ask_size_raw: int

    @property
    def bid(self) -> float:
        return self.bid_raw / FIXED_SCALAR

    @property
    def ask(self) -> float:
        return self.ask_raw / FIXED_SCALAR


def catalog_meta(path: str) -> dict[str, str]:
    """``instrument_id`` / ``price_precision`` / ``size_precision`` from the file."""
    import pyarrow.parquet as pq

    meta = pq.ParquetFile(path).schema_arrow.metadata or {}
    return {k.decode(): v.decode() for k, v in meta.items()}


def read_quotes(path: str, batch_rows: int = 4096) -> Iterator[RecordedQuote]:
    """Every quote in a catalog ``quote_tick`` file, in file order, lazily."""
    import pyarrow.parquet as pq

    cols = ["bid_price", "ask_price", "bid_size", "ask_size", "ts_event"]
    row = 0
    for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_rows, columns=cols):
        d = batch.to_pydict()
        for bid, ask, bsz, asz, ts in zip(
            d["bid_price"],
            d["ask_price"],
            d["bid_size"],
            d["ask_size"],
            d["ts_event"],
            strict=True,
        ):
            yield RecordedQuote(row, ts, raw(bid), raw(ask), raw(bsz), raw(asz))
            row += 1


def pace(prev_ts: int | None, ts: int, speed: float, max_gap_s: float) -> float:
    """Seconds to wait before emitting a quote recorded at ``ts``."""
    if prev_ts is None or ts <= prev_ts:
        return 0.0
    return min((ts - prev_ts) / 1e9 / speed, max_gap_s)


@dataclass
class ReplayCursor:
    """Where the replay is. Shared in-process between the data client and the strategy."""

    source: str
    instrument: str
    row: int = -1
    recorded_ts: int = 0
    laps: int = 0


@dataclass
class FeedSignal:
    """``XADD algobots:feed:<node>`` at most once per ``every_s`` of node time."""

    client: Any
    node: str
    every_s: float = 1.0
    maxlen: int = 3600
    received: int = 0
    written: int = 0
    _last_ns: int | None = None

    def on_quote(self, *, ts_init: int, bid: str, ask: str, cursor: ReplayCursor | None) -> bool:
        self.received += 1
        if self._last_ns is not None and ts_init - self._last_ns < self.every_s * 1e9:
            return False
        self._last_ns = ts_init
        fields = {
            "source": cursor.source if cursor else SYNTHETIC,
            "instrument": cursor.instrument if cursor else "",
            "node_ts": str(ts_init),
            "recorded_ts": str(cursor.recorded_ts) if cursor else "",
            "row": str(cursor.row) if cursor else "",
            "laps": str(cursor.laps) if cursor else "",
            "bid": bid,
            "ask": ask,
            "received": str(self.received),
        }
        self.client.xadd(feed_key(self.node), fields, maxlen=self.maxlen, approximate=True)
        self.written += 1
        return True


__all__ = [
    "DEFAULT_PATH",
    "FEED_PREFIX",
    "FIXED_SCALAR",
    "SYNTHETIC",
    "FeedSignal",
    "RecordedQuote",
    "ReplayCursor",
    "catalog_meta",
    "feed_key",
    "pace",
    "raw",
    "read_quotes",
]
