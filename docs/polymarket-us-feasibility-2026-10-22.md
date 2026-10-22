# Polymarket US — feasibility note for demo feed #2 (research only)

Date: 2026-10-22 · Probed live from .243 (AWS us-* egress, US IP) · Card: ALG-3411
Scope: PUBLIC DATA ONLY. No account, no orders, no keys — per demo law (paper first).

## Question
After Kalshi green, can Polymarket US serve as the second feed leg of the
feed trio (Binance + Polymarket + IBKR, ALG-3353)?

## Findings (all measured, 19:40–19:50 UTC Oct 22 2026)

1. **No US geoblock on public data.** polymarket.com → 200 (134 ms),
   gamma-api.polymarket.com/markets → 200 (44 ms), clob.polymarket.com/ok → 200
   "OK" (169 ms), all from a US AWS IP, unauthenticated.
2. **A structural twin of KXBTC15M exists: `btc-updown-15m`.** Slug pattern
   `btc-updown-15m-<interval-start-epoch>`; e.g. live interval
   `btc-updown-15m-1792697400` = "Bitcoin Up or Down, Oct 22 3:30–3:45 PM ET".
   A `btc-updown-5m` series also exists if a tighter cadence is ever wanted.
3. **Real two-sided book.** gamma event carries outcomes ["Up","Down"],
   outcomePrices, bestBid/bestAsk (0.61/0.62, 1¢ spread), liquidity ≈ $16.4k;
   CLOB POST /books on the Up token returns full depth (resting size at 1¢..99¢).
4. **Real volume.** Last 4 settled 15m intervals: $21.1k, $15.9k, $16.1k
   ($53.0k total; one late-created dud at $20). This is a traded market,
   not a quote skeleton.
5. **Evidence tooling works.** GET clob /prices-history?market=<token>&interval=1h
   → 57 points at 1-min fidelity → marimo evidence charts are feasible
   with zero new dependencies.
6. **Settlement semantics DIFFER from Kalshi (the one real gotcha).**
   Polymarket resolves Up if the **Chainlink TWAP** of the interval ≥ the
   open price. Kalshi KXBTC15M settles its strike vs the exchange mark at
   close, and our feed records `strike`. A Polymarket observer has no strike:
   the honest analog is the interval open price / relative resolution. The
   ledger schema (strike field) tolerates floats today, but a decision is
   needed on what goes in that column — flagged below, NOT implemented.

## Schema mapping sketch (not implemented)
- event ← slug (`btc-updown-15m-<ts>`); outcome ← resolution Up=1/Down=0
- mkt_yes_bid/ask/mid ← CLOB Up-token best bid/ask/mid at decision time
- p/conf ← 0.5 / 0.0, p_source "none" — same neutral posture as the Kalshi
  observer until a forecaster is wired (GATE-VERDICT-v2: never feed the
  book mid in as p)
- strike ← OPEN QUESTION (see gotcha above)

## Open questions (need Pat or a later run)
- **US account eligibility**: public data is open from US IPs, but whether
  US retail onboarding is live (post QCEX acquisition) could not be verified
  without creating an account — out of scope for a research-only note.
- **Second feed wiring**: workers/ledger read ONE feed path today. Adding
  observations_pm.jsonl needs a router/config decision → should be its own
  Paperclip card, not snuck into an observer PR.

## Recommendation
GREEN as data feed #2. A `polymarket_observer.py` would be ~the same shape
as `kalshi_observer.py` (~150 LOC, stdlib only, 20 s poll, atomic rewrite).
Execution there is a separate, later conversation (venue diversification
after the Kalshi demo loop proves out end-to-end).
