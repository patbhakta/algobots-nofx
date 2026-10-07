"""Bar source for the template paper runner (ALG-3281).

The demo box has no licensed equities feed, so templates run on a
**synthetic, deterministic** bar series: the close at bar ``n`` of a symbol
is a closed-form function of ``(symbol, cadence, n)``, a sum of two
symbol-phased cycles plus hashed noise around a per-symbol base price. Every
process computes the same bar for the same timestamp, nothing is path
dependent, and the cycles guarantee crossovers and RSI swings for a demo.
It is labelled ``SOURCE`` everywhere it shows: it is not market data.

Swap in a real feed by replacing ``bars``; the runner only needs closed bars
ending at or before ``end_ts``.
"""

from __future__ import annotations

import hashlib
import math

from algobots.strategies.eval import Bar

SOURCE = "SYNTHETIC BARS · deterministic · not market data"
CADENCE_S = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
BASE = {"SPY": 570.0, "QQQ": 490.0, "AGG": 98.0, "GLD": 245.0}


def _unit(*key: object) -> float:
    """Deterministic uniform in [-1, 1) from a key."""
    h = hashlib.sha256(":".join(map(str, key)).encode()).digest()
    return int.from_bytes(h[:8], "big") / 2**63 - 1.0


def close(symbol: str, cadence: str, n: int) -> float:
    base = BASE.get(symbol) or 50.0 + 200.0 * (_unit(symbol, "base") + 1) / 2
    phase = math.pi * (_unit(symbol, "phase") + 1)
    slow = 0.030 * math.sin(2 * math.pi * n / 97 + phase)
    fast = 0.012 * math.sin(2 * math.pi * n / 23 + 2 * phase)
    noise = 0.003 * _unit(symbol, cadence, n)
    return round(base * (1 + slow + fast + noise), 2)


def last_closed(cadence: str, now: float) -> int:
    """Index of the most recent bar that has closed at ``now`` (bar n spans [n, n+1) * step)."""
    return int(now // CADENCE_S[cadence]) - 1


def bar_ts(cadence: str, n: int) -> float:
    """Close time of bar ``n``."""
    return float((n + 1) * CADENCE_S[cadence])


def bar(symbol: str, cadence: str, n: int) -> Bar:
    o, c = close(symbol, cadence, n - 1), close(symbol, cadence, n)
    wick = abs(_unit(symbol, cadence, n, "w")) * 0.001 * c
    return Bar(open=o, high=round(max(o, c) + wick, 2), low=round(min(o, c) - wick, 2), close=c)


def bars(symbol: str, cadence: str, last: int, count: int) -> list[Bar]:
    """``count`` bars ending at (and including) bar index ``last``."""
    return [bar(symbol, cadence, n) for n in range(last - count + 1, last + 1)]
