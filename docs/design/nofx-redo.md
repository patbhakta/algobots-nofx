# A09 NoFX Redo — Design Language Record

Packet A09 redo ([ALG-3337](/ALG/issues/ALG-3337)). Board directive
[ALG-3336](/ALG/issues/ALG-3336) (user-created Oct 13 2026): **the warm-paper /
SETS styling is superseded.** The A09 investor-facing storyboard is rebuilt on
**NoFX** — the flat, dark, effects-free vocabulary already shipping on `/demo`
since ALG-3288 (`src/algobots/demo/theme.py`).

This file records the directive, the token table with measured contrast, and
the simplicity-first rules the tests enforce.

## Supersession

- [`shelpid-sets-dashboard-spec.md`](shelpid-sets-dashboard-spec.md) is
  superseded by this document (banner added at its top). Do not implement from
  it; it is kept for history.
- `warm-paper-design-system.md` describes the previous warm-paper system and
  the grain/motion machinery this redo deletes. It is historical; the A09
  source of truth is now `src/algobots/dashboard/design/tokens.py` +
  `css.py` on the NoFX palette.
- Deleted outright: `src/algobots/dashboard/design/grain.py` (texture is an
  effect; NoFX has none) and the texture/motion toggles, their JS/localStorage
  handling, `GRAIN`/`MOTION_MS`/`SHADOW` tokens, and the grain/motion tests.
  `components.settings()` remains exported for API compatibility with the
  `/demo` consumers but is no longer rendered by the storyboard.

## NoFX token table (measured)

Base values are the `/demo` terminal theme verbatim. Ratios are WCAG contrast
ratios measured with the A09 token math (`tokens.contrast`), rounded to 2
decimals. Every text token clears AA (>= 4.5:1) on every dark surface, so no
adjustment was needed: `ADJUSTMENTS` is empty. Tightest pair: `muted` on
`raised` at 4.75:1.

| Token | Value | Role | on bg | on panel | on raised |
|---|---|---|---|---|---|
| `bg` | `#0a0d10` | base surface | — | — | — |
| `panel` | `#0f1418` | panel surface | — | — | — |
| `raised` | `#151b21` | raised surface / inputs / hover | — | — | — |
| `ink` | `#d6dde4` | primary text | 14.21 | 13.52 | 12.66 |
| `muted` | `#7c8794` | secondary text | 5.33 | 5.07 | 4.75 |
| `rule-faint` | `#1d252d` | hairline rule | — | — | — |
| `rule-strong` | `#2b3540` | strong rule / borders | — | — | — |
| `positive` | `#2ecc71` | P&L gain, run-ok | 9.27 | 8.81 | 8.25 |
| `negative` | `#ff5c5c` | P&L loss, failure | 6.44 | 6.12 | 5.73 |
| `attention` | `#e0a33a` | warnings, DEMO DATA accents | 8.78 | 8.35 | 7.82 |
| `focus` | `#5aa9ff` | links, focus ring | 7.94 | 7.55 | 7.07 |

Non-text: `focus` (the focus ring, a state indicator) clears WCAG 1.4.11 3:1
on every surface (7.07:1 worst). The rule tokens are decorative hairline
separators, not state indicators, and are not held to 3:1 — same as `/demo`.

Typography is mono-first, straight from `/demo`: the
`ui-monospace, "JetBrains Mono", "SFMono-Regular", Menlo, Consolas,
"Liberation Mono", monospace` stack everywhere, with tabular (lining) numerals
for all financial values; body 12.5px, meta 11.5px, metric value 17px,
line-height 1.45.

## Simplicity-first: the no-effects rules

`tests/packets/A09/test_a09_nofx_guard.py` enforces these on the built sheet
and pages, and the token tests enforce "no effect tokens exist":

- **No motion**: no `@keyframes`, no `transition`, no `animation`, no motion
  tokens, no `prefers-reduced-motion` handling — nothing moves, so there is
  nothing to reduce.
- **No texture**: no grain tile, no `data:image` URIs, no canvas/feTurbulence.
- **No depth effects**: no gradients, no `box-shadow`/`text-shadow`, no
  `filter`/`backdrop-filter`, no `perspective`, no `will-change`.
- **No radius flourishes**: `border-radius` does not appear at all
  (`RADIUS = "0"`); the `/demo` terminal core has none either.
- **Flat surfaces and 1px solid rules** only: backgrounds are solid token
  colors, separation comes from `rule`/`rule-strong` borders.
- **No settings surface**: the storyboard ships no texture/motion toggles and
  no localStorage handling; the only query parameter is `?audit=1` (the
  headless layout-overflow report), which is kept.

Markup compatibility is unchanged: `components.py` class names and structure
are byte-identical to the previous revision so the `/demo` pages that import
and style `components` are unaffected (the `tests/demo` lane proves it).
