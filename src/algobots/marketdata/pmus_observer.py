"""Polymarket US (polymarket.us) btc-updown-15m forward observer: feed #3 (ALG-3411).

Run on the host as ``python3 -I src/algobots/marketdata/pmus_observer.py``
(stdlib only). Writes ``observations.jsonl`` with the same decide/settle shape as
the Kalshi observer (``kalshi_observer.py``): one row per 15-minute interval,
``outcome: null`` until the venue publishes settlement, atomic in-place rewrite.

Venue: QCX LLC (CFTC DCM), public gateway ``gateway.polymarket.us`` — no key,
no account, no orders (docs.polymarket.us). Unlike the global .com observer
(``polymarket_observer.py``) there is no strike-basis caveat here: the venue
itself publishes the strike as ``assetPriceTerms.priceToBeat`` at window open
and the final ``settlementPrice`` after close, both on the CF Benchmarks BRTI
(60 one-second prints averaged in the minute before each boundary). So
``strike_basis`` and ``settle_basis`` are the same index, and each settled row
carries a self-consistency check ``settle_consistent``: the published binary
must equal ``settle_price >= strike``.

Endpoints (verified live from .243/.245, Oct 23 2026):
- ``/v1/events?slug=btc-updown-15m-YYYY-MM-DD-HHMMz`` → event + nested market
  (market slug is ``cpc-`` + event slug; status ``MARKET_STATUS_OPEN`` while live)
- ``/v1/markets/{slug}/bbo`` → bestBid/bestAsk/sharesTraded/openInterest
  (404 outside the live window)
- ``/v1/markets/{slug}/settlement`` → ``{"settlement": 0|1}`` (404 until published,
  lags close by a few minutes)

``p`` follows the same law as the Kalshi feed: the neutral 0.5 with
``p_source: "none"`` — the book is recorded as evidence (``mkt_yes_bid``/
``mkt_yes_ask``/``mkt_mid``), never fed in as a signal (GATE-VERDICT-v2).
Evidence only: NOT wired into the paper workers.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

GATEWAY = "https://gateway.polymarket.us"
SERIES = "btc-updown-15m"
INTERVAL = 900
SETTLE_GIVE_UP = 48 * 3600


def _get(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "algobots-pmus-observer/1"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None  # venue's "not live yet / not published yet"
        raise


def slug_for(open_ts: float) -> str:
    """PM-US names each interval by its START time: btc-updown-15m-2026-10-23-0815z."""
    slot = int(open_ts) // INTERVAL * INTERVAL
    return datetime.fromtimestamp(slot, UTC).strftime(f"{SERIES}-%Y-%m-%d-%H%Mz")


def _ts(iso: str | None) -> float | None:
    if not iso:
        return None
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _px(obj: dict | None) -> float | None:
    """PM-US money fields are {"value": "81641.70", "currency": "USD"} or null."""
    try:
        return float((obj or {})["value"])
    except (KeyError, TypeError, ValueError):
        return None


def neutral_signal(_market: dict) -> tuple[float, float, str]:
    """Same law as the Kalshi feed: no forecaster wired, p stays neutral."""
    return 0.5, 0.0, "none"


class Observer:
    def __init__(
        self,
        feed: Path,
        get: Callable[[str], object] = _get,
        signal: Callable[[dict], tuple[float, float, str]] = neutral_signal,
        decide_window: float = 300.0,
    ):
        self.feed, self.get, self.signal, self.decide_window = feed, get, signal, decide_window

    def market(self, event_slug: str) -> dict | None:
        evs = (self.get(f"{GATEWAY}/v1/events?slug={event_slug}") or {}).get("events") or []
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

    def decide(self, slug: str, open_ts: int, now: float) -> tuple[dict | None, str | None]:
        m = self.market(slug) or {}
        terms = m.get("assetPriceTerms") or {}
        strike = _px(terms.get("priceToBeat"))
        if m.get("status") != "MARKET_STATUS_OPEN" or strike is None:
            return None, f"{slug}: not decidable (status={m.get('status')} strike={strike})"
        bbo = (self.get(f"{GATEWAY}/v1/markets/{m['slug']}/bbo") or {}).get("marketData") or {}
        bid, ask = _px(bbo.get("bestBid")), _px(bbo.get("bestAsk"))
        if bid is None or ask is None:
            return None, f"{slug}: not decidable (no two-sided book)"
        p, conf, source = self.signal(m)
        return {
            "event": slug,
            "market": m["slug"],
            "venue": "polymarket-us",
            "strike": strike,
            "strike_basis": "venue-priceToBeat-cf-brti",
            "settle_basis": "cf-brti-60s-avg",
            "outcome": None,
            "ts": now,
            "p": p,
            "conf": conf,
            "p_source": source,
            "open_ts": _ts(terms.get("windowStart")) or float(open_ts),
            "close_ts": _ts(terms.get("windowEnd")) or float(open_ts + INTERVAL),
            "mkt_yes_bid": bid,
            "mkt_yes_ask": ask,
            "mkt_mid": round((bid + ask) / 2, 4),
            "shares_traded": _px({"value": bbo.get("sharesTraded")}),
            "open_interest": _px({"value": bbo.get("openInterest")}),
        }, None

    def settle(self, r: dict, now: float) -> bool:
        st = self.get(f"{GATEWAY}/v1/markets/{r['market']}/settlement") or {}
        outcome = st.get("settlement")
        if outcome not in (0, 1):
            return False  # not published yet; retry next pass
        r["outcome"] = int(outcome)
        r["settled_ts"] = now
        m = self.market(r["event"]) or {}
        settle_px = _px((m.get("assetPriceTerms") or {}).get("settlementPrice"))
        if settle_px is not None:
            r["settle_price"] = settle_px
            r["settle_consistent"] = int(settle_px >= float(r["strike"])) == r["outcome"]
        return True

    def poll(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        rows = self.read()
        seen = {r.get("event") for r in rows}
        out: dict = {"ts": now, "decided": None, "settled": [], "errors": []}

        open_ts = int(now // INTERVAL) * INTERVAL
        slug = slug_for(open_ts)
        if slug not in seen and now - open_ts <= self.decide_window:
            try:
                row, err = self.decide(slug, open_ts, now)
                if row:
                    rows.append(row)
                    out["decided"] = slug
                else:
                    out["errors"].append(err)
            except Exception as e:  # noqa: BLE001 — API down: retry next poll
                out["errors"].append(f"{slug}: {e}")

        for r in rows:
            close_ts = float(r.get("close_ts") or 0)
            if r.get("outcome") is not None or now < close_ts or now - close_ts > SETTLE_GIVE_UP:
                continue
            try:
                if self.settle(r, now):
                    out["settled"].append(r["event"])
            except Exception as e:  # noqa: BLE001
                out["errors"].append(f"{r['event']}: {e}")

        if out["decided"] or out["settled"]:
            self.write(rows)
        return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--feed", default="/opt/laya/pmus/observations.jsonl")
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
                    "inconsistent": sum(1 for r in rows if r.get("settle_consistent") is False),
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
