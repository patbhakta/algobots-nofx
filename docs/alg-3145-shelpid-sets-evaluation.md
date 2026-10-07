# [ALG-3145] R&D Evaluation: Shelpid/SETS Dashboard & Evolution Engine

**Card:** [ALG-3145](http://100.101.235.117:3100/ALG/issues/ALG-3145) · **Assignee:** [AlgoBots R&D](http://100.101.235.117:3100/ALG/agents/fc49f730-259d-4e6e-b5f5-67984371cc7d) · **Author:** Pat (CEO)  
**Evaluated Target:** [Shelpid/SETS (SETS MACHINE)](https://github.com/Shelpid/SETS) @ commit `72f85bd` (2026-09-23)  
**Primary Verification Run:** Node v24.19.0, Headless Chromium 153.0.8010.12 (Playwright), Linux x86_64  

---

## 1. Executive Verdict & Core Recommendation

- **Overall Verdict:** **SALVAGE-PARTS (Dashboard UX & Visual Design Language) / SKIP (Trading Strategy & Genetic Search Engine)**.
- **One-Line Why:** The codebase delivers the cleanest, most responsive, and most honest visual representation of candidate strategy lifecycles, tournament selection, and paper execution seen in our research series; however, the underlying GA grid is simple parameter curve-fitting that lags buy-and-hold (+8.4% vs +11.4%), confirming our Zero Free Alpha doctrine.
- **Immediate Action:** Provide the formal Dashboard Element Specification (§5) to the Design Technologist and Tech Lead for incorporation into the **NoFX Warm-Paper Dashboard (A09/A10/S3.3)**.

---

## 2. License, Provenance & IP Verification

- **Primary Source:** [https://github.com/Shelpid/SETS](https://github.com/Shelpid/SETS)
- **License:** **MIT License** (Copyright (c) 2026 SETS MACHINE contributors). Clean permissive license with zero copyleft or AGPL taint.
- **Font Assets:** SIL Open Font License 1.1 (`JetBrains Mono`, `Space Grotesk` stored in `dist/assets/fonts/`).
- **Dependencies:** **Zero runtime dependencies**. Vanilla HTML5, CSS3, and ES6 modules on `<canvas>`. Total bundle is ~660 KB uncompressed, ~280 KB gzipped.
- **Data Source:** Bundled Binance public market data (2,399 hourly BTCUSDT candles from 2026-06-23 to 2026-09-22). No proprietary data or API keys required.
- **Commercial IP Safety:** Safe to adopt patterns, component layout, and visual algorithms without legal restriction.

---

## 3. Automated Verification & Spike Evidence

### 3.1 Automated Test Suite
The test suite (`tests/*.test.mjs`) was executed locally with Node 24:
```bash
node --test tests/*.test.mjs
```
**Results (8/8 PASS, 857.5 ms total):**
- `✔ bundled data is sane (6.07ms)`: 2,399 hourly bars, monotonically increasing 3600s intervals, low ≤ open/close ≤ high.
- `✔ rolling stats are causal and correct (0.89ms)`: Rolling mean, standard deviation, and breakout high are strictly causal (bar $j$ cannot see bar $j+1$).
- `✔ grid bot: fills levels, takes profit, pays fees (2.39ms)`: Adverse-first execution (buys -> stop -> TP), fees applied at 0.04% per fill.
- `✔ grid bot: stop loss closes the whole position (0.63ms)`: Deepest level stop execution verified.
- `✔ signals only use closed bars (4.66ms)`: Mutating candle 501 does not alter candle 500 signal.
- `✔ genomes stay inside bounds after mutation (6.71ms)`: 500 Gaussian mutations stay bounded within min/max ranges; integer genes remain integers.
- `✔ evolution is deterministic per seed and keeps every species alive (571.69ms)`: Seed 2026 produces byte-for-byte identical histories across runs.
- `✔ leader backtest is reproducible (145.14ms)`: Re-running out-of-sample tape matches stored metrics.

### 3.2 Live Browser & Visual Verification
Using headless Chromium 153 via Playwright, the dashboard was served on `http://127.0.0.1:8765/index.html?seed=2026&warm=50&paused`:
- **Desktop (1440×900, DPR=2.0):** Clean layout, 0 console errors, steady 60 FPS animation loop, crisp canvas rendering.
- **Mobile (390×844, DPR=2.0):** Responsive stacking verified. Playwright DOM query confirmed:
  `{ clientWidth: 390, scrollWidth: 390, bodyScrollWidth: 390 }` -> **Zero horizontal overflow.**
- **Interactivity:** Ray-casting / state selection verified. Inspecting node switches the Genome panel to `GENOME · INSPECTING` displaying parent lineage and historical performance side-by-side.

All high-resolution screenshot evidence has been captured and stored under `artifacts/ALG-3145/screenshots/` and `docs/research/sets-machine/`:
- Full desktop view: `sets-dashboard-1440-full.png`
- Full desktop inspecting view: `sets-dashboard-1440-inspecting.png`
- Full mobile view: `sets-dashboard-390-full.png`
- Panel 01 (Header): `01-header-hdr-1440.png`, `01-header-hdr-390.png`
- Panel 02 (Controls): `02-controls-bar-1440.png`, `02-controls-bar-390.png`
- Panel 03 (Evolution Ring): `03-evolution-ring-1440.png`, `03-evolution-ring-390.png`
- Panel 04 (Fitness History): `04-fitness-history-1440.png`, `04-fitness-history-390.png`
- Panel 05 (Gene Pool Mesh Graph): `05-gene-pool-mesh-1440.png`, `05-gene-pool-mesh-390.png`
- Panel 06 (Leader Genome): `06-genome-leader-1440.png`, `06-genome-leader-390.png`
- Panel 06b (Inspected Genome): `06b-genome-inspecting-1440.png`, `06b-genome-inspecting-390.png`
- Panel 07 (Selection Funnel): `07-selection-funnel-1440.png`, `07-selection-funnel-390.png`
- Panel 08 (Kelly Sizing): `08-kelly-sizing-1440.png`, `08-kelly-sizing-390.png`
- Panel 09 (Grid Engine Chart): `09-paper-grid-chart-1440.png`, `09-paper-grid-chart-390.png`
- Panel 10 (Order Grid & Execution Log): `10-order-grid-log-1440.png`, `10-order-grid-log-390.png`

---

## 4. Analysis vs. AlgoBots Edge Doctrine & Harness

### 4.1 The Rare Honesty of SETS
Unlike standard crypto trading bots that claim inflated Sharpe ratios, SETS openly reports:
1. **Buy & Hold Outperformed:** Over the 30-day OOS period, Buy & Hold made **+11.4% (7.7% DD)**, while the top evolved grid bot made **+8.4% (5.3% DD)**.
2. **Short OOS Window:** 30 days is an overfit filter, not a proof of edge.
3. **Selection Re-use:** Selecting the leader from OOS survivor candidates reuses the out-of-sample data, creating a selection optimism bias.
4. **Phantom Win Rates from Wide Stops:** High win rates (80–90%) are an artifact of grid DCA spacing with wide stops (up to 12% below the lowest tier), which have catastrophic left-tail risk during trend reversals.

### 4.2 Comparison with AlgoBots Decision-Quality Harness
- **SETS Engine:** Evaluates parameter combinations via genetic search (tournament selection, uniform crossover, Gaussian mutation). It is fundamentally brute-force curve fitting on historical candles.
- **AlgoBots Harness (ALG-3074 / ALG-3086 / S2.2):** Tests model conviction against multi-seed random controls. If a decision rule cannot beat a randomized coin-toss across $\ge 5$ seeds, it is discarded.
- **Verdict on Engine:** **SKIP**. We will not adopt SETS's genetic algorithm or grid logic. Our algorithmic edge comes from governed signals, portfolio mandate clamps, and deterministic order planning.

---

## 5. Dashboard Element Specification for Design Technologist

The following 7 elements from SETS are recommended for adoption into the AlgoBots **Warm Paper Design System (A09/A10)**.

### Element 1: Evolution / Evaluation Lifecycle Ring
- **Purpose:** Visualize the cyclical lifecycle of strategy evaluation (Observe -> Hypothesize -> Mutate -> Test -> Select -> Deploy).
- **SETS Implementation:** 2D Canvas circular ring drawing 5 concentric arcs with radial pulsing dots indicating the active stage.
- **Warm Paper Translation:**
  - Background track: `var(--color-rule-faint)` (`#D4CEC1`).
  - Active stage arc: `var(--color-focus)` (`#326982`) with a single-shot pulse `var(--dur-edge-pulse)` (400ms).
  - Center typography: Stage title in `var(--color-ink)` (`#292722`, 13px tabular mono), duration counter in `var(--color-muted)` (`#686358`).
  - Accessibility: Full SVG with `<title>` and `aria-label="Lifecycle stage: Testing candidate 4 of 12"`.

### Element 2: Strategy Fleet Cluster / Topology Graph
- **Purpose:** Real-time visual map of the active strategy fleet, showing parentage, family clustering, and promotions/retirements.
- **SETS Implementation:** Force-directed 4-cluster canvas graph (one per species). Nodes pulse on birth, connect via bezier lineage curves, and flash red on death.
- **Warm Paper Translation:**
  - Layout: Bounded canvas or SVG with 4 cluster centroids representing AlgoBots strategy archetypes (e.g. Statistical Arbitrage, Trend Following, Liquidity Provision, Risk Clamp).
  - Nodes: Sized by allocated capital or conviction score (radius 3px to 10px).
  - Colors: Mapped to Warm Paper semantic hues (`#266F4B` for active/healthy, `#895912` for throttled/quarantine, `#B43732` for circuit-breaker halted).
  - Motion: Lineage pulses restricted to real events using `--dur-edge-pulse` (400ms). When feed disconnects, display "Topology Frozen".

### Element 3: Interactive Strategy Inspector (Side-by-Side Validation)
- **Purpose:** Clicking any node in the topology opens a dedicated inspector comparing candidate parameters against validation baselines.
- **SETS Implementation:** Click canvas node -> Genome panel immediately switches title from `GENOME · LIVE LEADER` to `GENOME · INSPECTING #ID`, rendering 8 gene bars and side-by-side Train vs OOS return/drawdown metrics.
- **Warm Paper Translation:**
  - Drawer/Panel component: Uses standard `panel(financial=True)` with `DEMO DATA` / `PAPER` badges.
  - Parameter rows: Key-value rows with tabular numeric values (`font-variant-numeric: tabular-nums`).
  - Validation metrics: Clean comparative grid: In-Sample vs Out-of-Sample vs Random Baseline.

### Element 4: Multi-Gate Selection Funnel & Kelly Sizing
- **Purpose:** Transparent visualization of strategy survival criteria and capital allocation sizing.
- **SETS Implementation:**
  - Selection Funnel: Vertical bar stack showing Candidate Pool (96) -> Min Trades Gate (42) -> Drawdown Gate (18) -> Profit Gate (8) -> Promoted (1).
  - Kelly Sizing: Canvas curve of growth function $g(f) = W \ln(1 + fR) + (1 - W) \ln(1 - f)$ with peak marker $f^*$ and conservative half-Kelly reference line.
- **Warm Paper Translation:**
  - Funnel: CSS flexbox step progression. Rejected counts colored in `--color-muted`, survivors in `--color-positive`.
  - Kelly Panel: Replace theoretical Kelly curve with AlgoBots Capital Allocation Model (Risk Parity / Volatility Target / Hard Capital Reservation from A08).

### Element 5: Order Grid & Real-Time Execution Log
- **Purpose:** Display pre-committed limit orders across price levels and adverse-fill execution logging.
- **SETS Implementation:**
  - Order Grid Table: Columns for Level (`L1`..`L8`), Price, Size ($ USD), and Status (`PENDING`, `FILLED`, `CANCELLED`). Row highlights on hover and flashes royal blue on fill.
  - Execution Log: Monospace terminal feed with colored event tags (`BUY`, `TP`, `STOP`).
- **Warm Paper Translation:**
  - Reuse `components.action()` and `components.status()` tokens.
  - Orders: Explicitly tagged with account identifier and environment (`demo-01 · PAPER`).
  - Prices: Formatted via `components.money()` with explicit decimal alignment and currency tags.

### Element 6: Simulation & Replay Controls Bar
- **Purpose:** Deterministic control over playback and backtest speed.
- **SETS Implementation:** Horizontal button group: Pause/Play, Step, Speed (1x, 2x, 4x, 8x), Seed number input, Restart button. URL query parameters (`?seed=`, `?warm=`, `?speed=`) enable state sharing.
- **Warm Paper Translation:**
  - Buttons styled using Warm Paper `.btn` token (`#F5F1E8` background, 1px `#D4CEC1` border, 3px border-radius).
  - Keyboard shortcuts: `Space` (Pause/Resume), `Right Arrow` (Step).
  - URL state serialization: Include URL state synchronization for tenant/strategy/seed.

### Element 7: Zero-Horizontal-Overflow Responsive Architecture
- **Purpose:** Uncompromising mobile usability for on-call triage and monitoring.
- **SETS Implementation:** Clean CSS flexbox with media queries collapsing 3-column rows into single-column vertical stacks below 920px. Explicitly verified `scrollWidth === 390`.
- **Warm Paper Translation:**
  - Adopt SETS's responsive grid breakpoints:
    - Desktop: `1200px` max-width container with 2/3 column layout.
    - Tablet (`<920px`): Collapse multi-column rows (`.evo`, `.trio`, `.trade`) into vertical flow.
    - Mobile (`<560px`): Hide secondary sparklines and non-critical clocks, compress KPI stat sizes from 21px to 17px, switch grids to 2-column key-value cards.

---

## 6. Summary of Deliverables & Files

1. **Research Dossier:** This document (`docs/alg-3145-shelpid-sets-evaluation.md`).
2. **Visual Evidence:** High-resolution screenshots capturing all panels and viewports stored at `artifacts/ALG-3145/screenshots/` and `docs/research/sets-machine/`.
3. **Test Verification:** Verified Node test suite (8/8 PASS) and Playwright viewport test (`scrollWidth === 390`).
4. **Issue Comment & Disposition:** Full evaluation summary posted to Paperclip issue [ALG-3145](http://100.101.235.117:3100/ALG/issues/ALG-3145); issue transitioned to `done`.
