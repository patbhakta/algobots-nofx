"""The live Kalshi observer's book, as the node's market data (ALG-3411).

The Kalshi observer on the host (``/opt/laya/kalshi``, the laya loop) appends
one JSON line per observation to ``observations.jsonl``: every 15-minute
KXBTC market boundary carries the market's YES bid/ask snapshot (``ts`` is
the wall clock it was taken at). That cadence — one line per 15 minutes,
gaps when the loop pauses — is far sparser than both a paper venue and
hop 4's freshness rule need, so the node does what a data client for a
slow book does: it serves the *latest observed top of book* on its own
clock and re-stamps the observation's wall clock only when a new line
lands. Every feed signal says exactly that — ``node_ts`` is the re-serve
time, ``recorded_ts`` is the observation's, and the two only diverge by
the observation gap.

The parse is pure and file-shaped, so the module imports nothing from
Nautilus: tests run anywhere, and the client
(:class:`algobots.node.paper_node` ``KalshiLiveQuotes``) is the only thing
that touches the engine.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

DEFAULT_PATH = "/feeds/kalshi/observations.jsonl"


@dataclass(frozen=True)
class KalshiObservation:
    """One book snapshot: the observer's line ``row`` (1-based), wall clock, YES top."""

    row: int
    ts_ns: int
    market: str
    bid: Decimal
    ask: Decimal


def parse_line(row: int, line: str) -> KalshiObservation | None:
    """A jsonl line to an observation, or ``None`` if it carries no book.

    Lines the observer writes *before* a market opens (or between books)
    carry ``null`` bid/ask; they are not bad data, they are no data, and a
    client that quoted off them would invent a price. ``None`` keeps the
    previous book instead.
    """
    try:
        obj: Any = json.loads(line)
    except (json.JSONDecodeError, ValueError):
        return None  # a torn tail write; the completed retry follows it
    bid, ask = obj.get("mkt_yes_bid"), obj.get("mkt_yes_ask")
    ts = obj.get("ts")
    if bid is None or ask is None or ts is None:
        return None
    try:
        return KalshiObservation(
            row=row,
            ts_ns=int(float(ts) * 1_000_000_000),
            market=str(obj.get("market") or obj.get("event") or ""),
            bid=Decimal(str(bid)),
            ask=Decimal(str(ask)),
        )
    except (ArithmeticError, ValueError, TypeError):
        return None


class ObservationTail:
    """Byte-offset tail of a jsonl file: bootstrap the last book, then the new lines.

    Not a thread or a task — ``poll()`` is one non-blocking read, so the
    data client owns the pacing (it is the thing with a clock).
    """

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self._offset = 0
        self._row = 0
        self._partial = b""

    def bootstrap(self) -> KalshiObservation | None:
        """Scan the file once; position the tail at its end.

        Returns the newest observation that carries a book, so the node is
        quoting the live market immediately instead of waiting out the next
        15-minute boundary. ``row`` stays the file's own line number.
        """
        latest: KalshiObservation | None = None
        data = self.path.read_bytes()
        self._offset = len(data)
        lines = data.split(b"\n")
        self._partial = lines.pop()  # after the last \n, or b"" at a clean end
        for chunk in lines:
            self._row += 1
            if not chunk.strip():
                continue
            obs = parse_line(self._row, chunk.decode("utf-8", "replace"))
            if obs is not None:
                latest = obs
        return latest

    def poll(self) -> KalshiObservation | None:
        """The next completed observation appended since the last call, or ``None``.

        Yields at most one per call — a poll loop that drains one line per
        tick reads the file at the client's pace, never a burst.
        """
        try:
            with self.path.open("rb") as f:
                f.seek(self._offset)
                data = f.read()
        except FileNotFoundError:
            return None  # the observer recreates it; the last book stands
        if not data:
            return None
        self._offset += len(data)
        self._partial += data
        if b"\n" not in self._partial:
            return None  # still a torn line
        *done, self._partial = self._partial.split(b"\n")
        for chunk in done:
            self._row += 1
            if not chunk.strip():
                continue
            obs = parse_line(self._row, chunk.decode("utf-8", "replace"))
            if obs is not None:
                return obs
        return None


__all__ = ["DEFAULT_PATH", "KalshiObservation", "ObservationTail", "parse_line"]
