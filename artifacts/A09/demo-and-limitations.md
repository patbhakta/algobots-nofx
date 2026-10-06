# A09 — Demo and limitations

Packet A09 ([ALG-3105](/ALG/issues/ALG-3105)) delivers the warm paper design system and a
clickable fixture storyboard. The base is algobots `main` @ `48642df`. Everything here is synthetic
**DEMO DATA**. A fixture UI is not evidence of broker integration.

## Demo (`make demo-A09`)

Output captured in `demo-output.txt`:

```
[ok] storyboard: 20 pages + index, static, DEMO DATA on every page; grain tile sha256 ce5f5c978c43 at 3%
[ok] contrast: 24/24 text/surface pairs >= 4.5:1 (grain on and off); lowest 4.6:1
[adjusted] spec attention #946014 is 4.40:1 on paper (fails AA); shipped #895912 is 4.64:1 under grain
[rejected] action without environment: action 'Buy SPY' needs environment PAPER or LIVE, got None
[rejected] action with mismatched environment: action 'Buy SPY': environment LIVE != account PAPER
[paused] stale feed: approve disabled (True); pause stays available (True)
[unavailable] unknown valuation renders 'Unavailable', not 0: True
```

1. **Feature:** open `storyboard/index.html` from disk. It needs no server or network and links to
   4 screens × 5 fixture states: overview, advanced workspace, strategy studio, and invitation and
   onboarding × good, loss, empty, stale and unknown. The header toggles switch the texture and
   the motion.
2. **Failure path (account context):** an action without an environment, or with one that doesn't
   match the account, is refused at render time.
3. **Failure path (stale data):** with the feed disconnected, approval is disabled and the control
   says why. Pause and cancel stay available. Animation freezes.
4. **Failure path (unknown state):** an unreconciled valuation renders "Unavailable" with its
   reason, never 0. An UNKNOWN order offers "Request cancel".

## Outputs

- `storyboard/`: 21 static HTML pages, each self-contained with inline CSS, the grain tile and a
  small toggle script.
- `tokens.json`, `tokens.css`, `components.json`: the design tokens and the component inventory.
- `fixtures/*.json`: the deterministic fixture JSON, one file per state.
- `accessibility-contrast.json`: every text/surface pair with grain on and off.
- `screenshots/` (38 PNGs) and `layout-audit.json`: captured headless with Chrome for Testing 153
  (chrome-headless-shell, already on the host; nothing installed). Coverage:
  - every screen at 1920×1114, 1440×900, 1024×768 and 390×844 (good fixture);
  - every other state at 1440×900;
  - the overview's other states at 390×844;
  - texture off and motion off.
  No page overflows horizontally.
- `test-results/`: `junit.xml` and `pytest-summary.txt` from `make verify-A09`.

## Reference comparison: observed vs proposed

The uploaded NoFX MP4 (45.37 s, 1920×1114) is **not in any repository**, so this run could not
inspect it. "Observed" below means **observed (per roadmap text)**: the cues recorded in roadmap
§6 and the DASHBOARD-SPEC "Reference and visual direction" section. Nothing here comes from
watching the video. "Proposed" is this packet's design. Pat or the reviewer should compare it
against the video itself.

| Cue: observed (per roadmap text) | Proposed in A09 |
|---|---|
| Warm ivory paper-like surface | Paper `#EEE9DD` canvas, raised `#F5F1E8` for selected panels and forms, `color-scheme: light`; no dark tokens anywhere (tested) |
| Neutral paper/sandpaper texture (Pat's choice) | 96 px monochrome tile at 3%, stationary, below content; texture-off toggle |
| Fine dividers / thin editorial rules | 1px faint rules for panel boundaries and grids; 1px strong rules under the strips and headers |
| Compact tabular metrics, dense KPI strips | Two strips (portfolio; strategy stats with n, period and costs), mono tabular figures, headline values at 26px |
| Cost/liquidation distribution | Owned cost-basis distribution only. Liquidation estimates are omitted and labelled "no qualified source" |
| Order book | L2 depth bars when entitled. The unknown state shows "Unsupported: no L2 depth entitlement"; the stale state flags "resync pending" |
| Signal matrix | Strategy × instrument table with typed state, version, eligibility and last evaluation |
| Candle panels | Static SVG candles with symbol, venue, timeframe, timezone and warmup; gap flag in the stale state |
| Evolving flow → signal → decision → execute → hold topology | Trace rows market → signal → risk → order → position. Abstain stops at signal ("hold, no execution"). Outcomes cover APPROVED, REJECTED, AWAITING_APPROVAL, ABSTAIN, UNKNOWN and RECONCILING. Clicking a row opens its reason. One edge pulse plays for the newest real event only |
| Animations | Short, token-driven, one-shot. Reduced motion and motion off set them to 0ms |
| Reference returns are demonstration content | All values are synthetic and labelled DEMO DATA on every page and every financial panel |

## Known limitations

- **Reference video not inspected.** See the comparison above. Matching the visual direction
  needs a human look at the MP4.
- **Fonts:** no web fonts are bundled, to stay offline and avoid licensing. The rendering uses the
  host's fallback sans and mono (the screenshots show DejaVu-like faces). Choosing and licensing a
  font is open.
- **Accessibility:** the following are checked automatically:
  - contrast (AA, grain on and off);
  - status shown by glyph plus text;
  - a single h1, labelled inputs with `aria-describedby` errors, labelled nav and role=img;
  - focus-visible outlines;
  - reduced motion, both through the OS media query in a real browser and through the toggle.

  Not done:
  - a screen-reader pass with real assistive technology;
  - a full keyboard walk-through (the controls are native buttons, inputs, links and
    `<details>`);
  - an axe-style audit.
- **Not produced in A09:** the fixture-session interaction recording (video) and a performance
  baseline. The spec lists both under acceptance evidence. They are not A09 required artifacts and
  are left for A10, where the real shell exists.
- **Storyboard interactivity:** navigation, state switching, the texture and motion toggles, and
  the topology explain drawers work. Action buttons are inert, which is intentional: there is no
  backend in a fixture UI.
- **Mobile:** on narrow screens, wide tables scroll inside their panel rather than reflowing. The
  page itself never scrolls sideways (tested at 390 px).
- **Packaging:** the fixtures are Python data, not package files, so they survive a wheel install.
  The storyboard is built, not shipped.
- **Make target:** `Makefile` belongs to the `make-targets` resource (integration owner A01).
  A09's targets are proposed in `tests/packets/A09/make-targets.mk` and integrated verbatim in a
  separate `chore(make-targets)` commit. `test_a09_scope.py` checks that the two stay identical and
  that A09 commits stay inside A09's five paths.

## Recovery

A09 adds new modules only. Nothing imports them yet. To disable, stop importing
`algobots.dashboard.design` and `algobots.dashboard.fixtures` and drop the A09 make targets. The
last qualified version is `main` @ `48642df`.
