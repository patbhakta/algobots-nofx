# ALG-3309 — Strategy Sourcing Shortlist: Ecosystem Ports for KXBTC15M

**Status:** deliverable for [ALG-3309] — Pat directive (Oct 8) + CEO clarification (Oct 9).
**Scope:** candidates sourced from ecosystems (NautilusTrader examples, open-source algo
repos, published patterns), ranked by fit to our venue, with port-effort estimates.
**Explicitly out of scope:** Laya System One / Jev zero-shot tuning (directive: no further
tuning; their scores are unparameterized defaults, not verdicts — workers run as-is for
data continuity only). Model parameter tuning is a later phase; every candidate below is
port-and-run at fixed, frozen, published defaults.

## What "fit to venue" means here

The venue is the Kalshi BTC 15-minute paper pipeline (`src/algobots/demo/ledger.py`):

- One decision per KXBTC15M interval: **YES / NO / abstain**, computed from **prior
  intervals only** (no lookahead; feed rows are pre-scored at settlement).
- Deterministic end-to-end: same inputs → same decisions (System One rails, DSL eval is
  pure — no I/O, no clocks).
- Paper fills at the assumed 0.50 mid + Kalshi taker fee
  (`ceil(0.07 * C * P * (1-P))`); $100 sleeve per strategy;
  `RiskEnvelope(max_order_value=$15, max_daily_loss=$40)`.
- Coin-flip control (deterministic `sha256(event)`) is the baseline every candidate must
  beat out-of-sample; quality harness scores Brier vs coin 0.25, hit rate ± 1σ, `MIN_N=30`.
- Current DSL surface (`docs/strategies.md`): indicators `sma`/`ema`/`rsi`, ops
  `gt/gte/lt/lte/eq/crosses_above/crosses_below`, nested `all`/`any`, cadence `15m`.
- The PoC feed carries **no order book** (feed = strike, outcome, Laya P(up), Jev choice).

## Effort scale

| Scale | Meaning |
| --- | --- |
| **S** | DSL spec + studio definition + venue-eligibility row only — no new eval code. |
| **M** | New DSL indicator(s)/ops with pure-math eval + tests (bounded, reviewable). |
| **L** | New data source + decider input path + tests (touches feed/contracts). |

## Ranked shortlist

| # | Candidate | Source | Effort | Venue fit |
| --- | --- | --- | --- | --- |
| 1 | EMA-cross trend follower | NautilusTrader `examples/strategies/ema_cross.py` (v1.231.0, shipped in our venv) | **S** | Highest — canonical community example, DSL-native |
| 2 | RSI-2 mean reversion | Published: Connors, *Short Term Trading Strategies That Work* (widely replicated in open-source algo repos) | **S** | Highest — RSI already in DSL, published fixed defaults |
| 3 | Bollinger-Band mean reversion | NautilusTrader `examples/strategies/bb_mean_reversion.py`; Bollinger (1992) | **M** | High — canonical counter-trend counterpart to #1 |
| 4 | Volatility-gated trend (ATR regime filter over #1) | NautilusTrader `indicators/volatility` (ATR); TSMOM literature (Moskowitz–Ooi–Pedersen 2012) for the gate idea | **M** | Medium-high — better abstain quality, composite spec |
| 5 | Order-book imbalance taker | NautilusTrader `examples/strategies/orderbook_imbalance.py` | **L** | Strongest microstructure fit for event contracts, **blocked on data streaming ([ALG-3101](/ALG/issues/ALG-3101))** — no book in the feed today |

## Candidate details

### 1. EMA-cross trend follower (port of `ema_cross.py`) — S

- **Mapping:** 15m BTC bars; EMA(fast) vs EMA(slow). Fast above slow at interval open →
  YES (up); below → NO; crossing bars keep the side implied by the cross. Freeze at the
  example's own defaults (fast 10 / slow 20) — the point is the canonical community
  baseline, not tuned numbers.
- **Port surface:** pure DSL — `{"left": {"indicator":"ema","params":{"period":10}},
  "op":"crosses_above", "right": {...period 20}}` at `cadence: 15m`, plus a studio
  definition and a kalshi venue-eligibility row (A11 pattern: eligibility is per
  definition × venue).
- **Why ranked first:** zero new code; exercises deploy→freeze→worker→fill→settle with a
  strategy outsiders recognize; honest "no free alpha" control vs coin flip.
- **Estimate:** ~0.5 day including tests and demo wiring.

### 2. RSI-2 mean reversion (Connors port) — S

- **Mapping:** RSI(2) < 10 on prior bars → YES (bet up-reversion next interval);
  RSI(2) > 90 → NO; else abstain. Defaults are the published ones (period 2, 10/90
  bands) — frozen at deploy, never swept.
- **Port surface:** pure DSL — `rsi` exists; `lt`/`gt` against literal values. Only a
  studio definition + eligibility row.
- **Why ranked second:** published, widely replicated pattern with fixed defaults; the
  natural mean-reversion counterpart to #1; abstain-heavy profile suits the $15
  order cap.
- **Estimate:** ~0.5 day.

### 3. Bollinger-Band mean reversion (port of `bb_mean_reversion.py`) — M

- **Mapping:** close below lower band (SMA(20) − 2σ) → YES; above upper band → NO;
  inside bands → abstain. Example defaults (20, 2.0σ).
- **Port surface:** one new DSL indicator — rolling standard deviation (or a `bollinger`
  band indicator) — with pure-math eval + warmup rules; reuse `lt`/`gt`.
- **Why ranked third:** canonical Nautilus example and classic literature; adds the
  first DSL extension, proving the port path for new indicators (paves the way for #4/#5
  inputs).
- **Estimate:** ~1–1.5 days (indicator + validation + tests + demo wiring).

### 4. Volatility-gated trend (ATR filter over #1) — M

- **Mapping:** take #1's signal only when short-horizon realized vol (ATR(14) on 15m
  bars) sits inside a fixed band — abstain in dead chop. Gate thresholds frozen at
  literature-style defaults (e.g., median-vol quartiles computed once on a fixed
  training window and written into the frozen spec, never re-fit).
- **Port surface:** ATR indicator in DSL + a composite `all` spec (gate AND signal).
- **Why ranked fourth:** deterministic and explainable, but the gate is one more
  parameter set — only worth building after #1/#2 establish the baseline spread;
  defaults must be frozen before any observation of results to honor zero-tuning.
- **Estimate:** ~1.5 days.

### 5. Order-book imbalance taker (port of `orderbook_imbalance.py`) — L

- **Mapping:** best-bid/best-ask size ratio on the KXBTC15M book → YES/NO taker
  decision; abstain when the book is empty/thin (example's own guard).
- **Port surface:** new decider input path — book snapshots must reach the pipeline
  (feed contract + worker), plus a non-DSL decider module; taker-only fills still work
  at the assumed mid, so the settlement side is unchanged.
- **Why ranked last today (first after streaming lands):** the PoC feed has no book;
  this candidate is exactly the payoff of infra item (2) — data streaming
  ([ALG-3101](/ALG/issues/ALG-3101)). Sequence it after the feed carries quotes.
- **Estimate:** ~3–4 days incl. feed contract changes; blocked until ALG-3101 delivers
  book/quote data.

## Deliberately excluded

- **Market makers / grid quoter examples** (`market_maker.py`, `grid_market_maker.py`,
  `volatility_market_maker.py`): require two-sided quoting and book awareness; the paper
  venue fills takers at an assumed mid only — no maker path to model honestly.
- **ML/RL repos (FinRL et al.):** zero-free-alpha doctrine (ALG-3145/Jev-4763 finding);
  also inherently tuning-shaped, which this phase forbids.
- **Anything Laya/Jev-adjacent:** directive — no further tuning of those workers.

## Recommended build order

1 → 2 (both S, immediate, DSL-only) → 3 (M, proves DSL extension path) → 4 (M, composite)
→ 5 (L, after ALG-3101 streaming). Each lands as its own frozen $100 sleeve next to the
coin control, scored by the existing quality harness — same rails, no new scoring code.

Sequencing note (CEO clarification, Oct 9): infrastructure is the priority —
trades end-to-end ([ALG-3088](/ALG/issues/ALG-3088)), data streaming
([ALG-3101](/ALG/issues/ALG-3101)), frontend A10 shell + tenant auth
([ALG-3106](/ALG/issues/ALG-3106), [ALG-3099](/ALG/issues/ALG-3099)). Nothing in this
shortlist needs to precede those; #1/#2 are small enough to slot in alongside once the
pipeline is proving trades end-to-end.
