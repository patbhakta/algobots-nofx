# A09 — Demo and limitations (NoFX redo)

Packet A09 redo ([ALG-3337](/ALG/issues/ALG-3337), directive
[ALG-3336](/ALG/issues/ALG-3336)) rebuilds the investor-facing storyboard on the
**NoFX design language**: the flat, dark, effects-free vocabulary shipping on
`/demo` since ALG-3288. The base is algobots `origin/main` @ `a1a93c9`, branch
`feat/alg-3336-a09-nofx-redo`. The warm-paper/SETS styling is superseded
(`docs/design/nofx-redo.md`). Everything here is synthetic **DEMO DATA**. A
fixture UI is not evidence of broker integration.

## Demo (`make demo-A09`)

Output captured in `demo-output.txt`:

```
[ok] storyboard: 20 pages + index, static, DEMO DATA on every page; NoFX: flat dark, mono-first, no effects to toggle
[ok] contrast: 18/18 text/surface pairs >= 4.5:1 on dark surfaces; lowest 4.75:1
[rejected] action without environment: action 'Buy SPY' needs environment PAPER or LIVE, got None
[rejected] action with mismatched environment: action 'Buy SPY': environment LIVE != account PAPER
[paused] stale feed: approve disabled (True); pause stays available (True)
[unavailable] unknown valuation renders 'Unavailable', not 0: True
```

1. **Feature:** open `storyboard/index.html` from disk. It needs no server or network and links to
   4 screens × 5 fixture states: overview, advanced workspace, strategy studio, and invitation and
   onboarding × good, loss, empty, stale and unknown — all information content from the previous
   revision is kept. There are no toggles: NoFX has no texture and no motion, so there is nothing
   to toggle.
2. **Failure path (account context):** an action without an environment, or with one that doesn't
   match the account, is refused at render time.
3. **Failure path (stale data):** with the feed disconnected, approval is disabled and the control
   says why. Pause and cancel stay available.
4. **Failure path (unknown state):** an unreconciled valuation renders "Unavailable" with its
   reason, never 0. An UNKNOWN order offers "Request cancel".

## What changed in the redo

- **Tokens** (`tokens.py`): the `/demo` palette verbatim — bg `#0a0d10`, panel `#0f1418`,
  raised `#151b21`, ink `#d6dde4`, muted `#7c8794`, rule-faint `#1d252d`,
  rule-strong `#2b3540`, positive `#2ecc71`, negative `#ff5c5c`, attention `#e0a33a`,
  focus `#5aa9ff`. Every text token clears WCAG AA on every dark surface (measured, tightest
  4.75:1 muted on raised), so `ADJUSTMENTS` is empty. `GRAIN`, `MOTION_MS`, `SHADOW` deleted;
  `RADIUS = "0"`.
- **Grain deleted**: `grain.py` and its export are gone; texture is an effect.
- **Sheet rebuilt** (`css.py`): mono-first (`ui-monospace` stack from `/demo`), tabular numerals,
  1px solid rules, flat backgrounds, `color-scheme: dark`. No gradients, shadows, transitions,
  animations, border-radius or grain layer — enforced by `test_a09_nofx_guard.py`.
- **Storyboard** (`storyboard.py`): texture/motion toggles and their JS/localStorage handling
  removed; the `?audit=1` overflow-audit script kept (it now reports layout only). The
  "Animation frozen" note and pulse classes removed (nothing animates). Byte-for-byte
  determinism kept.
- **Components** (`components.py`): byte-identical. `settings()` stays exported for API
  compatibility but is no longer rendered; the `/demo` lane proves the shared-markup constraint.
- **Fixtures**: unchanged.
- **Docs**: `docs/design/nofx-redo.md` records the directive, the measured token table and the
  no-effects rules; `shelpid-sets-dashboard-spec.md` carries a superseded-by banner.

## Outputs

- `storyboard/`: 21 static HTML pages, each self-contained with inline CSS and the audit script.
- `tokens.json`, `tokens.css`, `components.json`: the NoFX tokens and the component inventory.
- `fixtures/*.json`: the deterministic fixture JSON, one file per state (unchanged).
- `accessibility-contrast.json`: every text/surface pair with its measured ratio (18 rows, all AA).
- `screenshots/` (36 PNGs) and `layout-audit.json`: captured headless with chrome-headless-shell
  from the Playwright cache (nothing installed). Coverage:
  - every screen at 1920×1114, 1440×900, 1024×768 and 390×844 (good fixture);
  - every other state at 1440×900;
  - the overview's other states at 390×844.

  No page overflows horizontally, and no metric, action, badge or status overflows its own cell.
  The PNGs are **not byte-reproducible**: re-running `make screenshots-A09` rewrites some files
  even on the same host, so a diff after a re-run is not a regression. `make verify-A09` does not
  touch them and stays clean.
- `test-results/`: `junit.xml`, `pytest-summary.txt` and the full `verify-A09.txt` transcript
  (verify + determinism + demo + screenshots + lint + regression counts).

## Known limitations

- **Review pending.** The Tech Lead reviews this branch independently (writer never approves);
  this document describes the build, not an approved state.
- **Rule contrast:** hairline rule tokens are decorative separators and are not held to WCAG
  1.4.11 3:1 (same as `/demo`); the focus ring — a state indicator — clears 3:1 everywhere
  (7.07:1 worst, measured).
- **Fonts:** no web fonts are bundled, to stay offline and avoid licensing. Rendering uses the
  host's monospace fallback (screenshots show a DejaVu-like face).
- **Accessibility:** contrast on dark surfaces, glyph+text statuses, single h1, labelled inputs,
  labelled nav, role=img labels and focus-visible outlines are checked automatically. Not done:
  a screen-reader pass with real assistive technology, a full keyboard walk-through (controls are
  native buttons, inputs, links and `<details>`), an axe-style audit.
- **Not produced in A09:** the fixture-session recording and performance baseline remain A10
  scope (the real shell).
- **Storyboard interactivity:** navigation, state switching and the topology explain drawers
  work. Action buttons are inert by design: there is no backend in a fixture UI.
- **Mobile:** on narrow screens, wide tables scroll inside their panel rather than reflowing.
  The page itself never scrolls sideways (tested at 390 px).
- **Base red:** `tests/demo/test_ledger.py::test_positions_and_orders_endpoints` fails
  byte-identically at `origin/main` `a1a93c9` (verified in a detached base worktree) —
  pre-existing, outside A09, reported for TL follow-up.
- **Make target:** unchanged; the A09 targets were already integrated. No Makefile changes in
  this redo. `test_a09_scope.py` now also checks ALG-3337 commits stay inside A09's five paths.

## Recovery

The previous warm-paper revision is the `feat/alg-3105-a09-design-system` history (merged as
`98d9423`). This redo is a normal forward commit on `feat/alg-3336-a09-nofx-redo`; reverting the
branch commits restores warm paper. Nothing outside A09's write scope is touched, and
`components.py` is unchanged, so `/demo` never depends on this redo.
