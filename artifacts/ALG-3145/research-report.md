# R&D Research Report: Shelpid/SETS ("SETS MACHINE")

**Issue:** ALG-3145  
**Author:** AlgoBots R&D (`fc49f730-259d-4e6e-b5f5-67984371cc7d`)  
**Target Repo:** `https://github.com/Shelpid/SETS`  
**License:** MIT License (contributors 2026), fonts SIL OFL 1.1  
**Verdict:** **SALVAGE-PARTS** (Adopt novel dashboard visualization language for NoFX warm-paper trading; skip evolutionary parameter search for alpha generation).

---

## 1. Executive Summary

SETS MACHINE is a self-contained browser application (660 KB dist, vanilla ES modules, zero runtime dependencies, no API keys, client-side canvas rendering) that evolves long-only grid-DCA strategies on 2,399 hourly BTCUSDT candles (June–September 2026). It employs an 8-gene genome across 4 strategy families, splits data into 70% in-sample training and 30% out-of-sample (OOS) validation, runs an out-of-sample survival gate, and replays the winning config on a simulated paper-trading grid.

### Key Finding
The repository's algorithmic search produces **zero genuine alpha**—a finding the author candidly demonstrates in their own benchmarks (buy-and-hold outperformed the best evolved strategy +11.4% vs +8.4%, while leader selection suffered from OOS data reuse and wide-stop survival bias). This aligns precisely with AlgoBots' **Edge Doctrine (Sep 19)** and **Jev-4763 finding (zero free alpha from off-the-shelf deciders)**.

However, the **dashboard visualization language is exceptional**. The live generation loop, force-directed species gene pool with lineage pulses, interactive node inspection comparing train vs. OOS metrics, natural selection funnel, Kelly growth curve, and responsive mobile stacking provide high-value UX patterns for AlgoBots' `/demo` and NoFX warm-paper terminal.

---

## 2. Repo Architecture & Verification

### 2.1 File Structure
```text
index.html              # Root redirect to dist/ (GitHub Pages compatible)
dist/
  index.html            # Dashboard semantic layout (10 panels)
  app.js                # Main event loop, simulation controller, canvas orchestrator
  style.css             # Responsive typography, CSS variables, grid/flex layouts
  engine/
    series.js           # Causal rolling mean, standard deviation, breakout highs
    bot.js              # GridBot execution engine (orders, adverse-first fills, fees)
    evolution.js        # Genome encoding, crossover, mutation, tournament selection
    rng.js              # Mulberry32 seeded PRNG for exact determinism
  ui/draw.js            # Canvas rendering (loop ring, fitness curve, gene mesh, Kelly, candles)
  data/candles.js       # 2,399 BTCUSDT 1h candles from Binance public API
  assets/               # Favicon, SVG logos, Space Grotesk and JetBrains Mono fonts
tools/fetch_data.py     # Python script refreshing candles from Binance API
tests/engine.test.mjs   # Node test runner suite (8 unit tests)
VALIDATION.md           # Empirical claims and reproduction notes
```

### 2.2 Local Execution & Spikes
- **Automated Tests:** All 8 unit tests in `tests/engine.test.mjs` execute and pass cleanly under Node 24 (`node --test tests/*.test.mjs` in 784ms):
  - Bundled data sanity: 2,399 candles, strictly 1-hour timestamps, valid OHLC ranges.
  - Causal rolling statistics: no look-ahead leakage.
  - Grid mechanics: adverse-first execution (buys, stops, then take-profits), 0.04% maker/taker fee deducted.
  - Genome mutation bounds: invariant bounds checking across 500 stochastic mutations.
  - Exact determinism: identical random seed produces identical generation trajectories across species.
  - Reproducibility: out-of-sample leader metrics match recorded results.
- **Headless Browser Capture:** Verified with Playwright on headless Chromium:
  - Desktop 1440×900: All 10 panels rendered with complete data.
  - Mobile 390×844: Panels stack vertically with zero horizontal overflow (`scrollWidth === clientWidth === 390px`).
  - Interactive node inspection: clicking any node in the gene pool displays candidate genome and comparative train vs. OOS stats side-by-side.

---

## 3. Algorithmic Assessment vs. AlgoBots Harness

### 3.1 SETS Algorithmic Mechanics
- **Genome (8 parameters):**
  - `family`: 4 categorical entry rules (Momentum, Mean Revert, Vol Breakout, Range Grid).
  - `lookback`: Rolling window (10–200 bars).
  - `entryZ`: Entry trigger threshold (0.2–2.5σ).
  - `levels`: Grid buy order count (2–8 levels).
  - `spacing`: Grid ladder interval (0.3–3.0%).
  - `mult`: Martingale sizing multiplier (1.0–2.0×).
  - `tp`: Take-profit offset from average entry (0.3–4.0%).
  - `stop`: Catastrophic stop below lowest ladder level (1.0–12.0%).
- **Evolutionary Operators:**
  - Population: 96 individuals (top 4 elites + 1 champion per species retained; 8 random immigrants + offspring via uniform crossover and Gaussian mutation $p=0.18$).
  - In-sample fitness: $\text{Train Return} - 0.6 \times \text{Max Drawdown}$ (penalized if trades $<4$).
  - Out-of-sample gate: $\text{OOS Return} > 1\%$, $\text{Max Drawdown} < 10\%$, $\text{Trades} \ge 3$, $\text{Win Rate} \ge 50\%$.

### 3.2 Fundamental Flaws & Author Candor
The repository author openly highlights the structural deficiencies of this approach:
1. **Loses to Buy & Hold:** Over the exact same 30-day out-of-sample window, BTCUSDT buy-and-hold achieved $+11.4\%$, whereas the best evolved strategy produced $+8.4\%$ (Seed 2026), $+8.3\%$ (Seed 7), and $+7.3\%$ (Seed 42).
2. **Selection Bias & Data Leakage:** The "leader" deployed to paper trading is chosen from the configs that passed the OOS gate. Reusing the OOS test set to rank and select the survivor invalidates out-of-sample independence (a textbook multiple-testing / peeking error).
3. **Grid/Martingale Curve Fitting:** DCA grids maintain artificially high win rates ($>80\%$) during range-bound markets by setting wide stops that are rarely triggered in short 30-day test windows. When a regime shift occurs, the accumulated downside wipes out prior gains.

### 3.3 Contrast with AlgoBots S2.2 Harness (`algobots.evals.harness`)
| Dimension | SETS MACHINE | AlgoBots S2.2 Decision-Quality Harness |
|---|---|---|
| **Objective** | Brute parameter optimization on price series | Decision quality evaluation of directional calls |
| **Statistical Gate** | Heuristic thresholds (Ret $>1\%$, DD $<10\%$) | Wilson score confidence lower bound over chance baseline |
| **Random Baseline** | None | Seeded `RandomBaseline` must score at/below chance (`random_at_or_below_chance`) |
| **Data Leakage Defense** | Leaks OOS data to rank leader | Forward-settling event ledger; pending calls strictly omitted from scoring |
| **Sizing Method** | Static grid multipliers ($1\text{--}2\times$) | Kelly sizing with empirical $\text{Beta}(2,2)$ prior shrinkage |
| **Verdict** | **SKIP** as an alpha generator | **RETAIN** AlgoBots S2.2 harness as gold standard |

---

## 4. IP, License & Security Audit

- **Code License:** MIT License, Copyright (c) 2026 SETS MACHINE contributors. Full permissive commercial reuse, modification, and distribution permitted.
- **Font Licenses:** SIL Open Font License 1.1 for bundled JetBrains Mono and Space Grotesk.
- **Market Data:** BTCUSDT hourly klines from Binance public API endpoints.
- **Code Reuse Decision:** **DO NOT COPY CODE WHOLESALE**. In accordance with AlgoBots engineering principles, we borrow UX patterns and design specifications, implementing them natively within our **Warm Paper Design System (`docs/design/warm-paper-design-system.md`)** using clean-room Python and vanilla components.

---

## 5. Salvage Value: UX Elements for NoFX Warm-Paper

We extract seven key UX patterns to incorporate into AlgoBots' warm-paper trading terminal:

1. **Cycle State Ring:** Visual representation of the live agent loop (Observe $\to$ Debate $\to$ Risk Gate $\to$ Order Ticket $\to$ Fill $\to$ Reflect).
2. **Strategy Gene Pool Topology:** Interactive canvas showing active strategies, candidate mutations, species clustering, and lineage pulses.
3. **Dual-Column Node Inspector:** Side-by-side inspection of strategy parameters, in-sample training metrics, and out-of-sample validation metrics.
4. **Natural Selection / Risk Gate Funnel:** Visualizing the multi-stage filter pipeline from raw generated signals to approved live/paper executions.
5. **Shrunk Kelly Sizing Display:** Visualizing the growth curve $g(f)$, win rate $W$, payoff ratio $R$, Half-Kelly fraction, and Bayesian shrinkage indicator.
6. **Execution Grid & Adverse-First Log:** Clear order ladder showing armed vs. pre-committed limit levels, take-profit, stop-loss, and adverse-first fill logs.
7. **Simulation Controls & URL State Sync:** Play/Pause, Step, 1×–8× speed, deterministic seed inputs, and bidirectional URL query sync (`?seed=`, `?speed=`, `?warm=`).
