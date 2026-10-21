# A05 demo and limitations

Instrument registry, recorded replay, and mixed-asset-class watchlist from the
A05 branch (`feat/alg-3101-a05-instrument-marketdata`). All data is deterministic
recorded fixtures — no live feeds were touched.

## Demo — two asset classes in one watchlist

As-of **Saturday 2026-10-31 15:00:30 UTC** (weekend): the equity and ETF are
closed with explicit weekend reasons, spot crypto and the perpetual are open 24x7,
and each row carries its data timestamps, source/sequence, age and configured precision.

| instrument | product | market status | last event (UTC) | available (UTC) | source#seq | age | price/qty decimals | ccy | data | eligible |
|---|---|---|---|---|---|---|---|---|---|---|
| XNAS:equity:AAPL | equity | CLOSED (weekend:Sat) | 2026-10-31T15:00:00+00:00 | 2026-10-31T15:00:01+00:00 | xnas-sip#5 | 29s | 2 / 0 | USD | fresh | no |
| XNYS:etf:SPY | etf | CLOSED (weekend:Sat) | — | — | —#— | —s | 2 / 0 | USD | stale | no |
| COINBASE:spot-crypto:BTC-USD | spot-crypto | OPEN (continuous-24x7) | 2026-10-31T10:02:00+00:00 | 2026-10-31T10:30:00+00:00 | coinbase-ws#6 | 16230s | 2 / 8 | USD | stale | yes |
| KRAKEN:spot-crypto:BTC-USD | spot-crypto | OPEN (continuous-24x7) | 2026-10-31T10:01:30+00:00 | 2026-10-31T10:01:31+00:00 | kraken-ws#2 | 17939s | 1 / 8 | USD | stale | yes |
| BYBIT:perpetual-swap:BTC-PERP | perpetual-swap | OPEN (continuous-24x7) | 2026-10-31T10:01:00+00:00 | 2026-10-31T10:01:00+00:00 | bybit-ws#2 | 17970s | 1 / 3 | USD | stale | yes |

As-of **Friday 2026-10-30 14:05:30 UTC** (regular equity session): both classes
open and fresh on their latest prints.

| instrument | product | market status | last event (UTC) | available (UTC) | source#seq | age | price/qty decimals | ccy | data | eligible |
|---|---|---|---|---|---|---|---|---|---|---|
| XNAS:equity:AAPL | equity | OPEN (regular-session:XNAS) | 2026-10-30T14:05:00+00:00 | 2026-10-30T14:05:01+00:00 | xnas-sip#4 | 29s | 2 / 0 | USD | fresh | yes |
| COINBASE:spot-crypto:BTC-USD | spot-crypto | OPEN (continuous-24x7) | — | — | —#— | —s | 2 / 8 | USD | stale | yes |

## Precision and explicit residuals (tick/lot boundaries)

| rounding | value | residual | increments |
|---|---|---|---|
| AAPL price 227.755 -> tick 0.01 (nearest) | 227.76 | -0.005 | 22776 |
| AAPL quantity 10.5 shares -> lot 1 (down) | 10 | 0.5 | 10 |
| BTC price 61000.14 -> tick 0.01 (nearest) | 61000.14 | 0.00 | 6100014 |
| BTC quantity 0.123456789 BTC -> lot 1e-8 (down) | 0.12345678 | 9E-9 | 12345678 |
| PERP price 61052.15 -> tick 0.1 (nearest) | 61052.2 | -0.05 | 610522 |

## FX conversion snapshots (reporting)

EUR/USD as-of 2026-10-30 12:00 UTC = 1.0850 (point-in-time). Unavailable pairs
raise `FxUnavailableError` — they are never reinterpreted as 1:1.

## Limitations

- **Calendars**: US equity sessions model Mon-Fri 09:30-16:00 America/New_York with
  DST via zoneinfo; **exchange holidays are not modeled** (a holiday weekday shows
  as open until a holiday calendar lands).
- **Perpetual swap is identity-only**: distinct executable ID, no execution support
  (A05 excludes options/futures execution; no universal-symbology claims).
- **Recorded fixtures only**: 5 instruments, 19 snapshots, 3 FX quotes; adapters are
  source-agnostic JSONL replays — Laya/Jev dropped per ALG-3309; no venue API is called.
- **Corrections amend quotes, not bars**: a later-published corrected price updates
  the point-in-time quote; bar history keeps what the tape printed at the time.
- **Seams left for their owners**: A06 `engine/workers/paper.py` ad-hoc Nautilus
  instruments, `engine/workers/fixture.py` synthetic quote stream, and `sleeve.py`
  Kalshi identities remain as-is; re-homing them onto this registry is out of scope.
- **External-environment cases are BLOCKED** and never claimed: this evidence is
  development/synthetic-paper only.

## Router mount (proposal through the api owner)

`/instruments` and `/market-data/status` are implemented in
`algobots.marketdata.routes` and mounted in `api/main.py` as a one-line-per-router
proposal per the A03/A04 mount precedent (see the A05 scope guard).
