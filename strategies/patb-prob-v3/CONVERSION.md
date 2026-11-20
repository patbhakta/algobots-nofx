# PatB Probability V3 — Conversion Spec (Pine → AlgoBots/Nautilus)

Source of truth: `patb_probability_v3.pine` (© patbhakta, MPL 2.0). Do not edit the .pine file.

## What the strategy actually computes (read before porting)

Three independent modules; only two carry tradeable signal:

1. **Structure module (context/state):** trailing max/min with pivot confirmation
   (prd=20). A `pos` state machine (0, ±1, ±2, ±n) tracks CHoCH → SMS → BMS
   transitions. Conditional probability tables: P(structure continuation |
   current state) — e.g. P(BMS follows | SMS after CHoCH). SM win/loss counter
   = the indicator's own profitability track record.
2. **Next Candle module (THE signal):** empirical P(next bar breaks prior high
   vs prior low | prior candle was green/red), measured at 0–4× percentage
   steps (default 1%). Emits: BIAS (bullish/bearish) + confidence %, every
   bar. Built-in backtest counter (NC WIN/LOSS) tracks whether the favored
   side got hit. **This is the order signal for the port.**
3. **Order-book ladder (viz only):** volume-profile ladder from candle closes.
   NOT part of v1 port; later a Data-tab overlay.

## Port design (law: strategies emit decisions; gateway/Nautilus executes)

- `patb_prob_v3.py` — pure-Python core, bar-driven: takes OHLCV bars, maintains
  the state machine + count matrices, exposes `on_bar(bar) -> Signal(bias,
  confidence, structure_pos, sm_stats)` plus the NC level probabilities.
- Wrapper A — **Nautilus Strategy** (live + backtest parity, same config).
  Signal rule for v1: on bar close, if NC confidence ≥ threshold (param,
  default 55%), emit market order in bias direction, qty param. Structure
  module gates: no longs when pos < -2, no shorts when pos > 2 (Pat can tune).
- Wrapper B — **marimo research notebook** (share-out artifact): replays
  history, shows probability tables, SM/NC win-loss, equity curve.
- Visualization (labels/lines/boxes/premium-discount zones) is NOT ported to
  the strategy — it belongs in the Data tab chart later.

## Params exposed on the strategy card (per Pat's card law)

structure period (20), response (7, toggle), NC pct step (1.0), NC levels (5),
confidence threshold (55), qty, direction gate toggle (structure filter on/off).

## Verification gate (no adoption without measurement)

- **Parity test:** run the Python core over ≥2000 bars of KXBTC history; the
  NC probability matrices and SM WIN/LOSS counts must match a reference
  implementation of the Pine logic on the same bars (hand-checked on a 50-bar
  sample by CEO + full-run match by script). Counts differ by >1 → fix before
  wiring.
- **Backtest first:** Nautilus backtest on available history BEFORE any live
  run. Report: hit rate vs coinflip baseline (we have 164 historical coinflip
  rounds to compare), drawdown, per-side bias.
- **Then live paper:** one instrument, qty 1, structure gate ON, 24h burn-in,
  dashboard-visible.

## Notes / open questions for Pat

- Pine uses chart-timeframe bars; port targets 5m bars on KXBTC to start
  (matches the coinflip series). Other timeframes = param change.
- The NC module's `alert.freq_once_per_bar` fires on every bar open; port
  fires on bar close (cleaner, avoids lookahead). Flagging the difference.
