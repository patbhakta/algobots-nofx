# Warm paper design system (A09)

Packet A09 ([ALG-3105](/ALG/issues/ALG-3105)). Source spec: the DASHBOARD-SPEC section embedded in
`stock-vaults/docs/algobots-v2-analysis-and-agent-roadmap.md` ("Dashboard specification — warm
paper trading workspace"). A10 and later dashboard packets consume this package. They do not copy
values out of it.

## Using it

```python
from algobots.dashboard.design.css import stylesheet        # one <style> block, all tokens as CSS vars
from algobots.dashboard.design import components as c        # action(), status(), money(), metric(), panel() ...
from algobots.dashboard.fixtures import fixture, STATES      # synthetic good/loss/empty/stale/unknown
```

`python -m algobots.dashboard.design build artifacts/A09` rebuilds the storyboard, `tokens.json`,
`tokens.css`, `components.json`, `accessibility-contrast.json` and the fixture JSON. The output is
byte-for-byte deterministic.

## Tokens

| Token | Spec value | Shipped | Why it differs |
|---|---|---|---|
| paper | `#EEE9DD` | same | |
| raised | `#F5F1E8` | same | |
| ink | `#292722` | same | |
| muted | `#686358` | same | |
| rule-strong | `#777064` | same | |
| rule-faint | `#D4CEC1` | same | |
| positive | `#27734E` | `#266F4B` | 4.45:1 on paper under 3% grain (below AA) |
| negative | `#B43732` | same | 4.60:1 under grain, passes |
| attention | `#946014` | `#895912` | 4.40:1 on plain paper; fails AA even without grain |
| focus | `#346D88` | `#326982` | 4.40:1 on paper under 3% grain |

The spec asks to "validate contrast in implementation". An adjustment is the smallest lightness
reduction that keeps the same hue and saturation and clears 4.6:1 in the worst case. The worst
case is a full-black grain pixel at the grain opacity under the text. The tests enforce three
rules:

- Every adjustment is needed: the spec value fails.
- Every adjustment is minimal: the result stays below 4.8:1, with a lightness change under 0.03.
- No other value drifts.

The lowest shipped text pair is 4.60:1, from muted and negative on paper under grain.

Type: system sans (Inter / Source Sans 3 if installed) at 15px body and 12.5px metadata. Headline
values are 26px. Financial values use a mono stack with `font-variant-numeric: tabular-nums`.
No web fonts are loaded, so pages work offline. Rules are 1px, corners are 3px, and the only
shadow is a 1px restrained one.

## Grain

There is one 96×96 8-bit grayscale tile, generated once from a fixed-seed xorshift PRNG using only
the stdlib. Its sha256 is pinned in the tests. It is embedded as a data URI on a `position: fixed`
layer at `z-index: -1`, with no animation and no pointer events, at 3% opacity (the spec allows
2–4%). There is no SVG filter, canvas or per-frame work. Texture off is `html[data-texture="off"]`
and is set by the header toggle (persisted) or `?texture=off`.

## Motion

| Interaction | Duration token |
|---|---|
| KPI update highlight (one shot; a real update only) | `--dur-kpi-highlight` 600ms |
| Depth bar width | `--dur-depth` 200ms |
| Signal / node selection | `--dur-signal-select` 150ms |
| Topology edge pulse (one shot, newest real event) | `--dur-edge-pulse` 400ms |
| Panel / drawer | `--dur-drawer` 200ms |

Every animation and transition reads a duration variable. Both `prefers-reduced-motion: reduce`
and `html[data-motion="off"]` (toggle or `?motion=off`) set all of them to 0ms and stop all
animation. Nothing loops. When the feed is disconnected, the KPI highlight and the edge pulse are
not emitted, and the topology says "Animation frozen".

## Components

`components.INVENTORY` lists them and `artifacts/A09/components.json` publishes the list. Three
invariants are enforced in code:

- `action()` raises unless it gets an account (id + label) and an environment of `PAPER` or
  `LIVE` that matches the account. It prints `account label · ENV` inside the control and in its
  aria-label. When disabled, it shows the reason.
- `money()`, `pct()` and `stat()` render a missing value as **Unavailable** with its reason, never
  as 0 or ∞. Signs are text (`+`, `−`) and screen readers also get "gain"/"loss", so values are
  readable without color.
- `status()` is a glyph plus a text label plus an aria-label. `panel(financial=True)` carries a
  DEMO DATA tag.

## Fixtures

`algobots.dashboard.fixtures` has five deterministic states, all `synthetic: true` with the label
`DEMO DATA`, `demo-` account ids and the SIMULATED broker:

- **good:** positive P&L, fills, a partial fill, a risk rejection, abstention, and an
  awaiting-approval trace.
- **loss:** negative return, an 11.85% drawdown alert, and a field-level strategy validation
  error.
- **empty:** a new account; every statistic is Unavailable with "no closed trades".
- **stale:** feed disconnected 7m 11s ago; approvals are paused while pause and cancel stay
  available; the invite has expired.
- **unknown:** valuations pending reconciliation, an UNKNOWN order, no L2 entitlement, and a
  9-trade sample below the 30-trade minimum.

The fixtures also cover mixed currency (USD and EUR, never converted) and the paper/live
distinction: the LIVE account's actions are disabled with "not authorized".
