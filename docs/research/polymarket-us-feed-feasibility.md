# Polymarket US as the second demo feed: feasibility (ALG-3357)

Pat's ruling (2026-10-22) puts Kalshi first and Polymarket US second, and the
second feed is not wired until the Kalshi loop is green. This note covers
reading Polymarket US market data only. It does not cover orders. All probes
below were run on 2026-10-22 between 07:58 and 08:05 UTC, with no credentials.

## Verdict: feasible, and it is a close twin of KXBTC15M

Polymarket US (QCX LLC, a CFTC designated contract market) lists a
**`btc-updown-15m`** series. It is the same instrument as Kalshi's KXBTC15M:

| | Kalshi KXBTC15M | Polymarket US btc-updown-15m |
|---|---|---|
| Question | BTC at close ≥ BTC at open | BTC at end ≥ BTC at start ("Up") |
| Settlement index | CF Benchmarks BRTI, 60-price average in the last minute | CF Benchmarks BRTI, 60-price average in the last minute |
| Windows | 15 min, :00/:15/:30/:45 | 15 min, :00/:15/:30/:45 |
| Market data auth | none (`api.elections.kalshi.com/trade-api/v2`) | none (`gateway.polymarket.us/v1`) |
| Weekly downtime | Thursday 03:00–05:00 ET (seen 2026-10-22) | was trading during Kalshi's window |

The rules text on market `cpc-btc-updown-15m-2026-10-22-0745z` reads: "settle
to Up if the Bitcoin price at 4:00AM ET ... is greater than or equal to the
price at 3:45AM ET ... Outcome sourced from CF Benchmarks' Bitcoin Real-Time
Index (BRTI) ... 60 BRTI prices are collected." Because the settlement index
is the same, each interval has one BTC outcome on both venues. The two
quotes then become a cross-venue pair on one contract.

## Public endpoints (verified)

Base `https://gateway.polymarket.us/v1`. No key.

| Need | Endpoint | Observed |
|---|---|---|
| Find the interval | `GET /search?query=btc up or down 15m` | event `btc-updown-15m-<YYYY-MM-DD>-<HHMM>z` (UTC start), one market each |
| Market by slug | `GET /market/slug/cpc-btc-updown-15m-<YYYY-MM-DD>-<HHMM>z` | 200; rules, start/end |
| Top of book | `GET /markets/<slug>/bbo` | 200; `bestBid`, `bestAsk`, `currentPx`, `state: MARKET_STATE_OPEN`, depth |
| Depth | `GET /markets/<slug>/book` | 200; `bids` / `offers` ladders |
| Outcome | `GET /markets/<slug>/settlement` | 404 while open; then `{"settlement": 0}` or `1` |

Slugs are deterministic from the UTC start time. A slug that hasn't started
yet returns 404 ("not found"), so an observer can derive it from the clock,
exactly as `kalshi_observer.event_for` does. One assumption still needs
checking: that `settlement: 1` means "Up" (the long side). Check it against a
known BRTI move before wiring.

Authenticated parts (not needed for a data feed): trading, portfolio, and
the private WebSocket live at `api.polymarket.us`, with signed requests (key
ID plus secret, timestamp within 30 s). Each member needs a verified
Polymarket US account. That is roadmap P4.5, not this feed.

## How it would plug in (after Kalshi is green)

1. Generalize `src/algobots/marketdata/kalshi_observer.py` into a venue
   interface with three methods: `event_for(close_ts)`, `market(event)` →
   status, strike, and quote, and `settle(event)` → 0/1. Add a Polymarket US
   implementation of about 60 lines over the four GETs above.
2. Write rows to a separate feed, for example `/opt/laya/polymarket-us/observations.jsonl`,
   with the same row schema. Do not mix two venues into one ledger stream.
   The ledger and the workers key every row on `event`, and both venues
   would book the same BTC move.
3. Getting these rows in front of the workers and /demo is the larger change. The
   workers and the API read exactly one `ALGOBOTS_DEMO_FEED_PATH`, and the
   paper instruments are named after the Kalshi ticker. A second feed means a
   per-venue feed path on the worker spec (A06) and a venue column on /demo.
   That is a sprint of its own. The observer is the easy part.

Cheaper interim option: record the Polymarket US BBO **into the Kalshi row**
as `pmus_yes_bid` / `pmus_yes_ask` / `pmus_mid`. The schema is open, and
`load_rows` ignores unknown keys. That shows the cross-venue spread in the
evidence notebook straight away, without touching the ledger or the workers.

## Risks

- New York AG sued QCX LLC on 2026-09-24 (unlicensed gambling). Per the press,
  the petition doesn't name the BTC product. A read-only data feed is
  unaffected, but trading through Polymarket US is a Pat decision.
- Rate limits are reported as about 25 requests/s per IP on the public
  gateway. These figures come from third-party articles and could not be
  confirmed in the official docs. An observer polling every 20 s uses about
  0.1 requests/s.
- The Polymarket US public API has no documented sandbox. That doesn't
  matter for reads.

## Sources

- [Polymarket US API introduction](https://docs.polymarket.us/api-reference/introduction),
  [Markets API overview](https://docs.polymarket.us/api-reference/market/overview),
  [Authentication](https://docs.polymarket.us/api-reference/authentication)
- [Official Python SDK](https://github.com/Polymarket/polymarket-us-python)
- [Polymarket launches 15-minute Bitcoin markets on US app (Crypto Briefing)](https://cryptobriefing.com/polymarket-15-minute-bitcoin-markets-us/)
- [Polymarket rolls out Bitcoin bets every 15 minutes as New York sues (CCN)](https://www.ccn.com/news/crypto/polymarket-rolls-out-bitcoin-bets-every-15-minutes-as-new-york-sues-over-gambling/)
- [Polymarket US API rate limits (QuantVPS)](https://www.quantvps.com/blog/polymarket-us-api-available)
- Live probes against `gateway.polymarket.us/v1` listed above (2026-10-22).
