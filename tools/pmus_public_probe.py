#!/usr/bin/env python3
"""Polymarket US public-API probe (ALG-3411 addendum, 2026-10-23).

Stdlib only, no key, no account. Proves the three endpoints a PM-US
observer needs: live-interval discovery, BBO on the open market, and
binary settlement of the previous interval.
Docs: https://docs.polymarket.us/api-reference (gateway.polymarket.us).
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.request

GATEWAY = "https://gateway.polymarket.us"


def get(path):
    req = urllib.request.Request(GATEWAY + path, headers={"User-Agent": "algobots-probe"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.load(r)


def slot_slug(offset_slots=0):
    now = int(time.time()) + offset_slots * 900
    slot = now // 900 * 900
    return dt.datetime.fromtimestamp(slot, dt.UTC).strftime(
        "btc-updown-15m-%Y-%m-%d-%H%Mz"
    )


def main():
    ev = get("/v1/events?slug=" + slot_slug(0))["events"][0]
    mkt = ev["markets"][0]
    print(f"live event  : {ev['slug']} closed={ev['closed']}")
    print(f"market      : {mkt['slug']} status={mkt.get('status')}")
    if mkt.get("status") != "MARKET_STATUS_OPEN":
        print("note: book not open yet (BBO 404s outside the live window)")
    bbo = get(f"/v1/markets/{mkt['slug']}/bbo")["marketData"]
    bid = (bbo.get("bestBid") or {}).get("value")
    ask = (bbo.get("bestAsk") or {}).get("value")
    traded, oi = bbo["sharesTraded"], bbo["openInterest"]
    print(f"bbo         : bid={bid} ask={ask} traded={traded} oi={oi}")
    for off in (-1, -2, -3):
        prev = get("/v1/events?slug=" + slot_slug(off))["events"][0]["markets"][0]
        if prev.get("status") != "MARKET_STATUS_RESOLVED":
            continue
        try:
            st = get(f"/v1/markets/{prev['slug']}/settlement")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        print(f"prior settle: {prev['slug']} -> {st}")
        break
    else:
        print("prior settle: none published yet (settlement lags close)")
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
