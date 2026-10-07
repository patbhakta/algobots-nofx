# Specification: NoFX Warm-Paper Dashboard Elements (Adapted from SETS MACHINE)

**Document:** `docs/design/shelpid-sets-dashboard-spec.md`  
**Target Consumer:** Design Technologist, Product Manager, Front-end Engineers  
**Source Analysis:** Shelpid/SETS ("SETS MACHINE", ALG-3145)  
**Design System Compliance:** AlgoBots Warm Paper Design System (A09 / `docs/design/warm-paper-design-system.md`)

---

## 1. Executive Context & Objectives

Pat flagged the Shelpid/SETS repository (`github.com/Shelpid/SETS`) highlighting its dashboard design language. While SETS MACHINE's underlying genetic algorithm is brute-force parameter fitting on historical candles (yielding zero free alpha, losing to buy-and-hold), its **visual presentation of algorithmic state, strategy topologies, selection funnels, and paper execution** is novel, intuitive, and highly engaging.

This specification details how to adapt seven key visual elements from SETS into the **AlgoBots Warm Paper Design System (A09)** for the NoFX warm-paper trading workspace and the `/demo` terminal.

---

## 2. Design System Tokens & Style Translation

SETS uses an aggressive dark neon aesthetic (`#080f1d` navy, `#00e5ff` cyan, `#3b82f6` electric blue). In AlgoBots, all elements must be fully refactored into the Warm Paper tokens to maintain strict compliance with A09:

| Role | SETS (Source) | AlgoBots Shipped Token | Notes |
|---|---|---|---|
| **Base Surface** | `#080f1d` (Dark Navy) | `var(--c-paper)` (`#EEE9DD`) | Textured with 3% fixed-seed noise tile |
| **Panel Surface** | `#0e172a` (Deep Blue) | `var(--c-raised)` (`#F5F1E8`) | 1px border `var(--c-rule-faint)` (`#D4CEC1`), 3px radius |
| **Primary Text** | `#e2e8f0` (White/Silver) | `var(--c-ink)` (`#292722`) | System sans stack, 15px body, 12.5px meta |
| **Secondary Text**| `#64748b` (Slate Gray) | `var(--c-muted)` (`#686358`) | High-contrast muted metadata |
| **Borders & Rules**| `#1e293b` (Subtle Navy)| `var(--c-rule-faint)` / `var(--c-rule-strong)` | 1px solid rules |
| **Positive Accent**| `#10b981` (Green) | `var(--c-positive)` (`#266F4B`) | Passes 4.45:1+ under 3% grain |
| **Negative Accent**| `#ef4444` (Red) | `var(--c-negative)` (`#B43732`) | Passes 4.60:1 under 3% grain |
| **Primary Focus** | `#00e5ff` (Cyan) | `var(--c-focus)` (`#326982`) | Deep slate cyan; accessible focus ring |
| **Warning / Edge** | `#f59e0b` (Amber) | `var(--c-attention)` (`#895912`) | Deep gold/amber |

---

## 3. Seven Core Dashboard Elements Spec

### Element 1: Decision Cycle State Ring
- **SETS Concept:** "EVOLUTION LOOP" ring showing stages: OBSERVE → MUTATE → TEST → SELECT → DEPLOY.
- **AlgoBots Translation:** **TradingAgents Decision Cycle Ring**.
  - **Stages:** `OBSERVE` (market feed ingested) → `DEBATE` (analyst bull/bear thesis) → `GATE` (risk breaker & harness check) → `EXECUTE` (order ticket submission) → `REFLECT` (settlement & calibration).
  - **Visual Anatomy:**
    - Segmented donut canvas/SVG (diameter 120–160px).
    - Inactive stages rendered in `var(--c-rule-faint)`.
    - Active stage highlighted in `var(--c-focus)` (`#326982`) with smooth progress arc sweep.
    - Central numeric readout showing generation / cycle tick count (`#104`, `#105`) and cycle duration.
  - **Motion Specs:**
    - Controlled by `--dur-edge-pulse` (400ms) on stage transition.
    - Freezes completely when `data-motion="off"` or `prefers-reduced-motion: reduce`.

### Element 2: Strategy Universe / Ensemble Cluster Mesh
- **SETS Concept:** "GENE POOL" canvas displaying 96 nodes positioned by genome traits, clustered by species (Momentum, Mean Revert, Vol Breakout, Range Grid), with parent-child lineage pulses.
- **AlgoBots Translation:** **Active Strategy Universe & Candidate Cluster Graph**.
  - **Clustering:** 4 quadrants/clusters representing strategy archetypes:
    1. Trend Following (`Laya`)
    2. Statistical Mean Reversion (`Jev`)
    3. Binary Event Prediction (`Coin`)
    4. Volatility / Grid Market-Making (`Alpha-Grid`)
  - **Node Representation:**
    - Coordinates calculated deterministically from strategy parameters (e.g., lookback window vs. entry threshold).
    - Node size scaled with assigned capital weight or S2.2 harness decision-quality score.
    - Outlines / halos on active paper-trading leaders.
    - Lineage edges connecting base strategies to evaluated parameter variations.
  - **Lineage Pulses:** Brief 400ms pulse along edge when candidate variation is evaluated.
  - **Interactions:**
    - Hovering any node renders pointer hand and highlights its ID.
    - Clicking any node freezes inspection onto that strategy (entering "INSPECTING" state).
    - Clicking empty space or pressing `Escape` clears inspection back to current active leader.

### Element 3: Dual-Column Genome & Strategy Inspector
- **SETS Concept:** "GENOME" panel displaying 8 gene meters, switching between "LIVE LEADER" and "INSPECTING [node]", with side-by-side Train vs. OOS stats.
- **AlgoBots Translation:** **Strategy Parameter Sheet & S2.2 Harness Verdict Pane**.
  - **Visual Anatomy:**
    - Header: `STRATEGY · LIVE LEADER` (default) vs `STRATEGY · INSPECTING [ID]` (on node select) with clear prompt: *"Click canvas or press Esc to return to leader"*.
    - Parameter Rows: Horizontal segmented tick meters (22 segments each) rendering key parameters (Lookback, Entry Z-Score, Grid Depth, Sizing Multiplier, Stop-Loss Envelope).
    - Comparison Footer: Split table showing In-Sample (Train) vs Out-of-Sample (Live/Test) performance:
      - Return (%) & Max Drawdown (%)
      - Trade count & Win rate (%)
      - S2.2 Harness Verdict: Wilson confidence lower bound vs chance level.

### Element 4: Natural Selection & Multi-Stage Gate Funnel
- **SETS Concept:** "NATURAL SELECTION" panel showing funnel: GENERATED → BACKTESTED → PASSED GATE → ELITE KEPT → DEPLOYED.
- **AlgoBots Translation:** **Decision Quality & Risk Gate Funnel**.
  - **Funnel Stages:**
    1. `GENERATED`: Raw candidate signals emitted by strategy models.
    2. `HARNESS GATED`: Passed S2.2 random-baseline gate (`Wilson LB > Chance`).
    3. `RISK CLEARED`: Passed risk envelope (max drawdown, concentration limits, kill-switch).
    4. `APPROVED`: Action Center clearance (Auto-approved or Semi-auto token granted).
    5. `EXECUTED`: Orders filled on paper/live exchange.
  - **Visual Anatomy:**
    - Stepped horizontal progress bars with primary bar (total volume) and inner fill (survivor volume).
    - Explicit rule badge displayed beneath: `GATE: WILSON LB > 50% · MAX DD < 10% · RISK ENVELOPE VERIFIED`.

### Element 5: Shrunk Kelly Sizing & Allocation Display
- **SETS Concept:** "KELLY SIZING" panel displaying growth curve $g(f)$, win rate $W$, payoff ratio $R$, Half-Kelly $f^*$, and shrunk trade count.
- **AlgoBots Translation:** **Bayesian Shrunk Kelly Sizing Calculator**.
  - **Mathematical Definition:**
    $$g(f) = W \ln(1 + fR) + (1 - W) \ln(1 - f)$$
    $$f^* = \max\left(0, W - \frac{1 - W}{R}\right)$$
  - **Bayesian Shrinkage Safeguard:**
    - Displays $W$ shrunk toward $50\%$ using a $\text{Beta}(2,2)$ prior to prevent small-sample optimism.
    - Tag: `N TRADES · SHRUNK PRIOR`.
  - **Visual Anatomy:**
    - High-impact headline: Half-Kelly allocation percentage (e.g., `14%`).
    - Canvas/SVG growth curve plotting $g(f)$ from $f = 0$ to $2f^*$, with peak marker.
    - 4-up metric grid: `WIN RATE W`, `PAYOFF R`, `HALF-KELLY f*`, `EDGE (E)`.

### Element 6: Paper Blotter, Order Grid & Adverse-First Log
- **SETS Concept:** "GRID ENGINE" chart and "ORDER GRID" table with PRE-COMMITTED ladder and reverse-chronological log.
- **AlgoBots Translation:** **NoFX Warm-Paper Blotter & Execution Grid**.
  - **Order Ladder Table:**
    - Columns: `LEVEL` (L1..L4, TP, SL), `PRICE` (tabular mono), `SIZE` ($ USD), `STATUS` (`FILLED`, `ARMED`, `% AWAY`).
    - Flashing highlight on newly filled level using `--dur-kpi-highlight` (600ms).
  - **Execution Log:**
    - Strict adverse-first execution order recorded: buy limits filled, then stops checked, then take-profits.
    - Fees explicitly accounted for ($0.04\%$ taker fee deducted per fill).
    - Status badges: `PAPER · SIMULATED FILLS`.

### Element 7: Deterministic Controls Deck & State Sync
- **SETS Concept:** Run/Pause, Step, 1×/2×/4×/8× speed, Seed input, URL query sync.
- **AlgoBots Translation:** **Simulation Control Deck**.
  - **Controls:**
    - Primary Action: `▶ RUN` / `❚❚ PAUSE` toggle (`c.action` styled).
    - Step Button: `STEP ›` (advances simulation by exactly 1 evaluation bar/generation).
    - Speed Selector: Segmented button group (`1×`, `2×`, `4×`, `8×`).
    - Deterministic Seed Input: Numeric field (`SEED 2026`) + `RESTART` / `NEW SEED`.
  - **URL Synchronization:**
    - Live two-way sync: `?seed=2026&speed=4&paused&warm=50`.
    - Loading a URL with a seed reproduces identical simulation runs down to individual order fills.

---

## 4. Mobile Responsiveness (390px Viewport)

SETS proves that a data-heavy algorithmic dashboard can work seamlessly on mobile when built with care:
- **Viewport Invariant:** At `390px` width (iPhone 12/13/14/15/16 standard), `document.documentElement.scrollWidth === 390px`. Zero horizontal scrolling or viewport blowout.
- **Layout Stacking:**
  - Multi-column grids (`.row.evo`, `.row.trio`, `.row.trade`) collapse to a single vertical column (`grid-template-columns: 1fr`).
  - Canvases dynamically resize using `devicePixelRatio` scaling while maintaining 100% container width.
  - High-density 4-up metric strips (`.kv4`) wrap into 2×2 grids.
  - Interactive touch targets are styled with minimum 44px tap targets.

---

## 5. Accessibility & Performance Guardrails

1. **Contrast Standards:**
   - Text elements must clear WCAG AA 4.5:1 (AlgoBots Warm Paper tokens provide 4.60:1 to 4.80:1 against grain).
2. **Offline-First / Zero External Requests:**
   - Zero web fonts or external CDN dependencies. System fonts (`Inter`, `Source Sans 3`, system sans, monospace) loaded locally.
3. **Motion Sensitivity:**
   - Both `prefers-reduced-motion: reduce` and `html[data-motion="off"]` (or `?motion=off`) freeze all canvas loop animations, line pulses, and background canvas updates.

---

## 6. Implementation Plan for Design Technologist

1. **Phase 1 (Storyboards & Mockups):**
   - Add new storyboard views in `algobots.dashboard.design.storyboard` demonstrating the Decision Ring, Strategy Universe Mesh, and Funnel using Warm Paper tokens.
2. **Phase 2 (Component Integration):**
   - Implement `CycleRing`, `ClusterMesh`, `SelectionFunnel`, and `KellyCurve` canvas/SVG components in `src/algobots/dashboard/design/components.py`.
3. **Phase 3 (/demo Integration):**
   - Wire components into `/demo` paper trading terminal in `src/algobots/demo/page.py`.
