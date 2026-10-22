"""Polymarket btc-updown-15m forward observer: feed #2 evidence (ALG-3411).

Run on the host as ``python3 -I src/algobots/marketdata/polymarket_observer.py``
(stdlib only). Writes ``observations.jsonl`` with the same decide/settle shape as
the Kalshi observer (``kalshi_observer.py``): one row per 15-minute interval,
``outcome: null`` until the venue reports resolution, atomic in-place rewrite.

It is deliberately **not** wired into the paper workers: the demo loop
(ALG-3357) runs on the Kalshi feed, and Polymarket rows differ in one semantic
that is still pending sign-off on the card:

- **Strike.** Kalshi exposes ``floor_strike`` (venue-reported open reference).
  Polymarket has no strike field: it settles "Up" if the Chainlink BTC/USD TWAP
  of the range is >= the price at the start of the range. This observer records
  the **Kraken XBTUSD 15m candle open** at the interval start as the effective
  strike (Coinbase BTC-USD candle open as fallback), tagged
  ``strike_basis``. Measured Oct 22: Kraken open 81334.4 vs the live Kalshi
  floor_strike 81333.30 — basis-consistent to ~1 USD. ``settle_basis`` records
  that the venue itself settles on Chainlink TWAP, so strike-vs-settle basis
  risk is real and visible in the data, not hidden.

Resolution lookup: closed crypto-series markets disappear from
``gamma /markets?slug=`` but remain under ``gamma /events?slug=`` with the
market nested (verified live, Oct 22). Decide uses ``/markets?slug`` (the
market object directly), settle uses ``/events?slug``.

``p`` follows the same law as the Kalshi feed: the neutral 0.5 with
``p_source: "none"`` — the market mid is recorded as evidence
(``mkt_yes_bid``/``mkt_yes_ask``/``mkt_mid``), never fed in as a signal
(GATE-VERDICT-v2).

Public data only: no auth, no orders, no account. US-IP verified (ALG-3411
feasibility note).
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

GAMMA = "https://gamma-api.polymarket.com"
KRAKEN = "https://api.kraken.com/0/public/OHLC?pair=XBTUSD&interval=15"
COINBASE = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
SERIES = "btc-updown-15m"
INTERVAL = 900
SETTLE_GIVE_UP = 48 * 3600


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "algobots-pm-observer/1"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def slug_for(open_ts: float) -> str:
    """Polymarket names each interval by its START epoch: btc-updown-15m-<ts>."""
    return f"{SERIES}-{int(open_ts) // INTERVAL * INTERVAL}"


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def kraken_open(open_ts: float) -> tuple[float, str] | None:
    """(price, basis) for the 15m candle opening at open_ts (matches Kalshi strike basis)."""
    rows = _get(KRAKEN).get("result", {}).get("XXBTZUSD") or []
    for r in rows:
        if r[0] == int(open_ts):
            return float(r[1]), "kraken-xbtusd-open"
    return None


def coinbase_open(open_ts: float) -> tuple[float, str] | None:
    from datetime import datetime, timezone

    s = datetime.fromtimestamp(open_ts, timezone.utc).isoformat()
    e = datetime.fromtimestamp(open_ts + INTERVAL, timezone.utc).isoformat()
    for c in _get(f"{COINBASE}?granularity=900&start={s}&end={e}"):
        if c[0] == int(open_ts):
            return float(c[3]), "coinbase-btcusd-open"  # [time, low, high, open, close, vol]
    return None


def effective_strike(open_ts: float) -> tuple[float, str] | None:
    for src in (kraken_open, coinbase_open):
        try:
            hit = src(open_ts)
        except Exception:  # noqa: BLE001 — exchange hiccup: try the fallback
            continue
        if hit:
            return hit
    return None


def neutral_signal(_market: dict) -> tuple[float, float, str]:
    """Same law as the Kalshi feed: no forecaster wired, p stays neutral."""
    return 0.5, 0.0, "none"


def _jlist(v) -> list:
    """gamma returns some list fields JSON-encoded as strings; normalize both forms."""
    if isinstance(v, str):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    return v if isinstance(v, list) else []


def settled_outcome(m: dict) -> int | None:
    """1 (Up) / 0 (Down) once the venue has resolved, else None."""
    if not m.get("closed"):
        return None
    try:
        prices = [float(x) for x in _jlist(m.get("outcomePrices"))]
        outcomes = _jlist(m.get("outcomes"))
    except (TypeError, ValueError):
        return None
    if "Up" not in outcomes:
        return None
    up = prices[outcomes.index("Up")]
    if up >= 1 - 1e-6:
        return 1
    if up <= 1e-6:
        return 0
    return None  # resolved-but-not-binary / still converging


class Observer:
    def __init__(
        self,
        feed: Path,
        get: Callable[[str], object] = _get,
        signal: Callable[[dict], tuple[float, float, str]] = neutral_signal,
        decide_window: float = 300.0,
    ):
        self.feed, self.get, self.signal, self.decide_window = feed, get, signal, decide_window

    def active_market(self, slug: str) -> dict | None:
        ms = self.get(f"{GAMMA}/markets?slug={slug}")
        return (ms or [{}])[0] or None

    def settled_market(self, slug: str) -> dict | None:
        evs = self.get(f"{GAMMA}/events?slug={slug}") or []
        mkts = (evs[0] or {}).get("markets") or [] if evs else []
        return mkts[0] if mkts else None

    def read(self) -> list[dict]:
        if not self.feed.exists():
            return []
        out = []
        for line in self.feed.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except ValueError:
                continue  # dropped on the next rewrite, like load_rows
        return out

    def write(self, rows: list[dict]) -> None:
        tmp = self.feed.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r) + "\n" for r in rows))
        os.replace(tmp, self.feed)

    def poll(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        rows = self.read()
        seen = {r.get("event") for r in rows}
        out: dict = {"ts": now, "decided": None, "settled": [], "errors": []}

        open_ts = int(now // INTERVAL) * INTERVAL
        slug = slug_for(open_ts)
        if slug not in seen and now - open_ts <= self.decide_window:
            try:
                m = self.active_market(slug) or {}
                quote_ok = m.get("active") and m.get("bestBid") and m.get("bestAsk")
                strike = effective_strike(open_ts)
                if quote_ok and strike:
                    price, basis = strike
                    p, conf, source = self.signal(m)
                    bid, ask = float(m["bestBid"]), float(m["bestAsk"])
                    rows.append(
                        {
                            "event": slug,
                            "market": m.get("conditionId"),
                            "venue": "polymarket",
                            "strike": price,
                            "strike_basis": basis,
                            "settle_basis": "chainlink-twap",
                            "outcome": None,
                            "ts": now,
                            "p": p,
                            "conf": conf,
                            "p_source": source,
                            "open_ts": float(open_ts),
                            "close_ts": _ts(m.get("endDate")) or float(open_ts + INTERVAL),
                            "mkt_yes_bid": bid,
                            "mkt_yes_ask": ask,
                            "mkt_mid": round((bid + ask) / 2, 4),
                        }
                    )
                    out["decided"] = slug
                else:
                    out["errors"].append(f"{slug}: not decidable (active={m.get('active')} strike={bool(strike)})")
            except Exception as e:  # noqa: BLE001 — API down: retry next poll
                out["errors"].append(f"{slug}: {e}")

        for r in rows:
            close_ts = float(r.get("close_ts") or 0)
            if r.get("outcome") is not None or now < close_ts or now - close_ts > SETTLE_GIVE_UP:
                continue
            try:
                m = self.settled_market(r["event"])
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"{r['event']}: {e}")
                continue
            outcome = settled_outcome(m or {})
            if outcome is not None:
                r["outcome"] = outcome
                r["settled_ts"] = now
                out["settled"].append(r["event"])

        if out["decided"] or out["settled"]:
            self.write(rows)
        return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feed", default="/opt/laya/polymarket/observations.jsonl")
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
            print(json.dumps(res), flush=True)
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
