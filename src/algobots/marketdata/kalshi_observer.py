"""Kalshi KXBTC15M forward observer: writes the demo feed (ALG-3357).

Run on the host as ``python3 -I src/algobots/marketdata/kalshi_observer.py``
(stdlib only, so no venv is needed). It writes ``observations.jsonl``, which the
paper workers and the /demo ledger read (``algobots.demo.ledger.load_rows``),
and keeps one row per 15-minute interval:

1. **Decide.** In the first ``--decide-window`` seconds of an interval, append
   a *pending* row (``outcome: null``) with the strategy signal ``p`` = P(up).
   ``demo.quality`` shows it as a pending call.
2. **Settle.** Once Kalshi reports the market's ``result``, the same row is
   rewritten in place with ``outcome`` 1/0, using an atomic replace. Only
   then does ``load_rows`` hand it to the ledger and the workers.

``p`` is **not** the market mid. The ledger's ``laya`` strategy trades
``p - 0.5`` as an edge and fills at an assumed 50c (``ledger.FILL_PRICE``). If
the book's own mid were fed in as ``p``, the ledger would buy at 50c contracts
the market prices away from 50c, and the gap would show up as profit nobody
could actually capture (GATE-VERDICT-v2: "a participant cannot monetize the
mid against itself"). The Laya model that used to supply ``p`` was archived on
2026-10-16, so ``p`` is the neutral 0.5 (``p_source: "none"``) and ``laya``
abstains with its own reason. The live quote at decision time is recorded as
``mkt_yes_bid`` / ``mkt_yes_ask`` / ``mkt_mid``, as evidence of how far the
50c fill assumption was from the book. Jev (a paid external API) is not
called, so ``jev`` abstains too. ``coin`` trades every interval.

Public market data only: no auth, no orders, no account.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = "https://api.elections.kalshi.com/trade-api/v2"
SERIES = "KXBTC15M"
INTERVAL = 900
ET = ZoneInfo("America/New_York")  # Kalshi tickers name the close in exchange time
SETTLE_GIVE_UP = 48 * 3600  # stop asking about a market this long after its close


def _get(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "algobots-kalshi-observer/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def event_for(close_ts: float) -> str:
    """The event ticker of the interval closing at ``close_ts`` (``KXBTC15M-26OCT220400``)."""
    return f"{SERIES}-{datetime.fromtimestamp(close_ts, ET).strftime('%y%b%d%H%M').upper()}"


def current_close(now: float) -> int:
    return (int(now // INTERVAL) + 1) * INTERVAL


def _price(m: dict, key: str) -> float | None:
    """A ``*_dollars`` quote as a float; an empty side (0) is None."""
    try:
        v = float(m.get(f"{key}_dollars") or 0)
    except (TypeError, ValueError):
        return None
    return v if v > 0 else None


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def neutral_signal(_market: dict) -> tuple[float, float, str]:
    """(p, conf, source) when no forecaster is wired: the ledger's laya arm abstains."""
    return 0.5, 0.0, "none"


class Observer:
    def __init__(
        self,
        feed: Path,
        get: Callable[[str], dict] = _get,
        signal: Callable[[dict], tuple[float, float, str]] = neutral_signal,
        decide_window: float = 300.0,
    ):
        self.feed, self.get, self.signal, self.decide_window = feed, get, signal, decide_window

    def market(self, event: str) -> dict | None:
        ms = self.get(f"{BASE}/markets?event_ticker={event}").get("markets") or []
        return ms[0] if ms else None

    def read(self) -> list[dict]:
        if not self.feed.exists():
            return []
        out = []
        for line in self.feed.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # load_rows skips it too; it is dropped on the next rewrite
        return out

    def write(self, rows: list[dict]) -> None:
        tmp = self.feed.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        os.replace(tmp, self.feed)  # readers see the old file or the new one, never half

    def poll(self, now: float | None = None) -> dict:
        """One observation pass. Returns what changed (for the log)."""
        now = time.time() if now is None else now
        rows = self.read()
        seen = {r.get("event") for r in rows}
        out: dict = {"ts": now, "decided": None, "settled": [], "errors": []}

        close = current_close(now)
        event = event_for(close)
        if event not in seen and now - (close - INTERVAL) <= self.decide_window:
            try:
                m = self.market(event)
                strike = (m or {}).get("floor_strike")
                if m and m.get("status") in ("active", "open") and strike:
                    p, conf, source = self.signal(m)
                    bid, ask = _price(m, "yes_bid"), _price(m, "yes_ask")
                    rows.append(
                        {
                            "event": event,
                            "market": m["ticker"],
                            "strike": float(strike),
                            "outcome": None,
                            "ts": now,
                            "p": p,
                            "conf": conf,
                            "p_source": source,
                            "open_ts": _ts(m.get("open_time")),
                            "close_ts": _ts(m.get("close_time")) or float(close),
                            "mkt_yes_bid": bid,
                            "mkt_yes_ask": ask,
                            "mkt_mid": round((bid + ask) / 2, 4) if bid and ask else None,
                        }
                    )
                    out["decided"] = event
                else:
                    out["errors"].append(f"{event}: not tradeable yet ({(m or {}).get('status')})")
            except Exception as e:  # noqa: BLE001 — exchange down / 503: retry next poll
                out["errors"].append(f"{event}: {e}")

        for r in rows:
            close_ts = float(r.get("close_ts") or 0)
            if r.get("outcome") is not None or now < close_ts or now - close_ts > SETTLE_GIVE_UP:
                continue
            try:
                m = self.market(r["event"])
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"{r['event']}: {e}")
                continue
            result = (m or {}).get("result")
            if result in ("yes", "no"):
                r["outcome"] = 1 if result == "yes" else 0
                r["settled_ts"] = now
                r["settle_value"] = (m or {}).get("expiration_value") or None
                out["settled"].append(r["event"])

        if out["decided"] or out["settled"]:
            self.write(rows)
        return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feed", default="/opt/laya/kalshi/observations.jsonl")
    ap.add_argument("--poll", type=float, default=20.0, help="seconds between passes")
    ap.add_argument("--decide-window", type=float, default=300.0)
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    feed = Path(a.feed)
    feed.parent.mkdir(parents=True, exist_ok=True)
    obs = Observer(feed, decide_window=a.decide_window)
    status = feed.with_name("observer.json")
    last_err = None
    while True:
        res = obs.poll()
        if res["decided"] or res["settled"] or res["errors"] != last_err:
            print(json.dumps(res), flush=True)  # journald / the unit's log file
        last_err = res["errors"]
        rows = obs.read()
        status.write_text(
            json.dumps(
                {
                    "last_poll": res["ts"],
                    "last_poll_utc": datetime.fromtimestamp(res["ts"], UTC).isoformat(),
                    "rows": len(rows),
                    "pending": sum(1 for r in rows if r.get("outcome") is None),
                    "last_errors": res["errors"],
                    "pid": os.getpid(),
                }
            )
        )
        if a.once:
            return
        time.sleep(a.poll)


if __name__ == "__main__":
    main(sys.argv[1:])
