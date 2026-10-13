# ruff: noqa: E501  (CSS template: one declaration block per line reads better than wrapped)
"""Stylesheet generated from the NoFX tokens (one source of truth for A10 to consume).

Simplicity-first, per the ALG-3336 board directive: mono-first typography with
tabular numerals, flat dark backgrounds, 1px solid rules. No gradients, no
shadows, no transitions, no animations, no border-radius, no grain layer —
tests/packets/A09/test_a09_nofx_guard.py enforces all of that on this sheet.
"""

from algobots.dashboard.design.tokens import (
    COLORS,
    RADIUS,
    RULE_WIDTH,
    SPACE,
    TYPE,
)


def custom_properties() -> str:
    lines = [f"  --c-{name}: {value};" for name, value in COLORS.items()]
    lines += [f"  --space-{k}: {v};" for k, v in SPACE.items()]
    lines += [
        f"  --font-mono: {TYPE['mono']};",
        f"  --fs-body: {TYPE['body_px']}px;",
        f"  --fs-meta: {TYPE['meta_px']}px;",
        f"  --fs-headline: {TYPE['headline_px']}px;",
        f"  --radius: {RADIUS};",
        f"  --rule: {RULE_WIDTH} solid var(--c-rule-faint);",
        f"  --rule-strong: {RULE_WIDTH} solid var(--c-rule-strong);",
    ]
    return ":root {\n  color-scheme: dark;\n" + "\n".join(lines) + "\n}\n"


def stylesheet() -> str:
    return (
        custom_properties()
        + f"""
html {{ background: var(--c-bg); color: var(--c-ink); }}
body {{
  margin: 0; font: var(--fs-body)/{TYPE["line_height"]} var(--font-mono);
  font-variant-numeric: tabular-nums lining-nums;
  background: var(--c-bg); color: var(--c-ink);
}}

a {{ color: var(--c-focus); }}
:focus-visible {{ outline: 2px solid var(--c-focus); outline-offset: 1px; }}
.sr-only {{ position: absolute; width: 1px; height: 1px; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}

.num, table.data td.n, .metric .value {{
  font-family: var(--font-mono); font-variant-numeric: tabular-nums lining-nums;
}}
.meta {{ font-size: var(--fs-meta); color: var(--c-muted); }}
.pos {{ color: var(--c-positive); }}
.neg {{ color: var(--c-negative); }}
.attn {{ color: var(--c-attention); }}

.chrome {{ position: sticky; top: 0; z-index: 2; background: var(--c-bg); }}
.demo-banner {{
  display: flex; gap: var(--space-3);
  flex-wrap: wrap; align-items: baseline; padding: var(--space-1) var(--space-4);
  background: var(--c-panel); border-bottom: var(--rule-strong);
  font: 600 var(--fs-meta)/1.4 var(--font-mono); letter-spacing: .06em; color: var(--c-ink);
}}
.demo-banner strong {{ color: var(--c-attention); }}
.demo-tag {{
  font: 600 10.5px/1 var(--font-mono); letter-spacing: .06em; color: var(--c-attention);
  border: {RULE_WIDTH} solid var(--c-attention); padding: 2px 4px;
}}

.app-header {{
  display: flex; flex-wrap: wrap;
  gap: var(--space-2) var(--space-4); align-items: center; padding: var(--space-2) var(--space-4);
  background: var(--c-panel); border-bottom: var(--rule-strong);
}}
.app-header .crumb {{ font-weight: 600; }}
.spacer {{ flex: 1 1 auto; }}
.badge {{
  font: 700 var(--fs-meta)/1 var(--font-mono); letter-spacing: .08em; padding: 3px 6px;
  border: 1px solid currentColor;
}}
.badge.env-paper {{ color: var(--c-focus); }}
.badge.env-live {{ color: var(--c-negative); background: var(--c-raised); }}

nav.screens {{
  display: flex; align-items: center; flex-wrap: wrap; gap: var(--space-1) var(--space-4);
  padding: var(--space-2) var(--space-4); border-bottom: var(--rule);
}}
nav.screens a {{ text-decoration: none; color: var(--c-muted); padding: 2px 0; }}
nav.screens a[aria-current="page"] {{ color: var(--c-ink); border-bottom: 2px solid var(--c-ink); }}
nav.states a {{ font-family: var(--font-mono); font-size: var(--fs-meta); }}

main {{ padding: var(--space-4); display: grid; gap: var(--space-4); max-width: 1880px; }}
.strip {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  border-top: var(--rule-strong); border-bottom: var(--rule); background: var(--c-panel);
}}
.metric {{ padding: var(--space-2) var(--space-3); border-right: var(--rule); min-width: 0; }}
.metric .label {{ font: var(--fs-meta)/1.3 var(--font-mono); color: var(--c-muted); text-transform: uppercase; letter-spacing: .04em; }}
.metric .value {{ font-size: clamp(15px, 1.5vw, var(--fs-headline)); line-height: 1.2; }}
.ccy {{ color: var(--c-muted); }}
.metric .value .ccy {{ font-size: .62em; }}
.metric .value .meta {{ white-space: normal; }}
.metric.compact .value {{ font-size: 15px; }}
.metric .value.unavailable {{ font-size: var(--fs-body); color: var(--c-muted); }}

.cols {{ display: grid; gap: var(--space-4); grid-template-columns: repeat(3, minmax(0, 1fr)); }}
.cols.two {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
.panel {{
  border: var(--rule); background: var(--c-panel); min-width: 0;
}}
.panel.raised {{ background: var(--c-raised); }}
.panel > header {{
  display: flex; gap: var(--space-2); align-items: center; justify-content: space-between;
  padding: var(--space-2) var(--space-3); border-bottom: var(--rule-strong);
  background: var(--c-raised);
}}
.panel > header h2 {{ margin: 0; font-size: 11.5px; font-family: var(--font-mono); text-transform: uppercase; letter-spacing: .05em; }}
.panel .body {{ position: relative; padding: var(--space-2) var(--space-3); overflow-x: auto; }}
.empty {{ color: var(--c-muted); padding: var(--space-3) 0; }}

table.data {{ width: 100%; border-collapse: collapse; font-size: var(--fs-body); }}
table.data th {{ text-align: left; font: 500 var(--fs-meta)/1.3 var(--font-mono); color: var(--c-muted); border-bottom: var(--rule-strong); padding: 4px 6px; }}
table.data td {{ border-bottom: var(--rule); padding: 4px 6px; vertical-align: top; }}
table.data td.n, table.data th.n {{ text-align: right; white-space: nowrap; }}
table.data tbody tr:hover {{ background: var(--c-raised); }}

.status {{ display: inline-flex; gap: 4px; align-items: baseline; font: 600 var(--fs-meta)/1.3 var(--font-mono); white-space: nowrap; }}
.status .glyph {{ font-family: var(--font-mono); }}
.status.ok {{ color: var(--c-positive); }}
.status.bad {{ color: var(--c-negative); }}
.status.warn {{ color: var(--c-attention); }}
.status.info {{ color: var(--c-focus); }}
.status.neutral {{ color: var(--c-muted); }}

.action {{
  position: relative;
  display: inline-flex; flex-direction: column; align-items: flex-start; gap: 1px;
  font: inherit; color: var(--c-ink); background: var(--c-raised); cursor: pointer;
  border: var(--rule-strong); padding: 4px 10px; text-align: left;
}}
.action .ctx {{ font: var(--fs-meta)/1.2 var(--font-mono); color: var(--c-muted); }}
.action[aria-disabled="true"] {{ cursor: not-allowed; color: var(--c-muted); border-style: dashed; }}
.action .why {{ font-size: var(--fs-meta); color: var(--c-attention); }}
.actions {{ display: flex; flex-wrap: wrap; gap: var(--space-2); }}

.bar {{ height: 10px; background: var(--c-rule-strong); }}
.bar > span {{ display: block; height: 100%; background: var(--c-muted); }}
.depth .bar {{ min-width: 48px; }}
.depth .bid > span {{ background: var(--c-positive); }}
.depth .ask > span {{ background: var(--c-negative); }}

.topology {{ display: grid; gap: var(--space-2); }}
.trace {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }}
.node {{
  font: var(--fs-meta)/1.2 var(--font-mono); border: var(--rule-strong);
  padding: 3px 6px; background: var(--c-raised); color: var(--c-ink);
  cursor: pointer;
}}
.node:hover, .node:focus-visible {{ border-color: var(--c-focus); }}
.edge {{ color: var(--c-muted); }}
details.explain {{ font-size: 13.5px; }}
details.explain[open] {{ background: var(--c-raised); padding: var(--space-2); border: var(--rule); }}

.steps {{ list-style: none; margin: 0; padding: 0; display: grid; gap: var(--space-2); }}
.steps li {{ display: flex; justify-content: space-between; gap: var(--space-2); border-bottom: var(--rule); padding: 4px 0; }}
.field {{ display: grid; gap: 2px; margin-bottom: var(--space-3); }}
.field label {{ font: var(--fs-meta)/1.3 var(--font-mono); color: var(--c-muted); }}
.field input {{ font: inherit; font-family: var(--font-mono); background: var(--c-bg); color: var(--c-ink); border: var(--rule-strong); padding: 4px 6px; max-width: 100%; box-sizing: border-box; }}
.field .err {{ color: var(--c-negative); font-size: var(--fs-meta); }}
.field input[aria-invalid="true"] {{ border-color: var(--c-negative); border-width: 2px; }}
.candles svg {{ width: 100%; height: 180px; display: block; }}

@media (max-width: 1100px) {{
  .cols {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 700px) {{
  .cols, .cols.two {{ grid-template-columns: minmax(0, 1fr); }}
  .strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  main {{ padding: var(--space-2); }}
  .wide {{ display: none; }}
  .app-header {{ padding: var(--space-1) var(--space-2); gap: 2px var(--space-2); }}
  .demo-banner {{ padding: 2px var(--space-2); }}
  .metric .value {{ font-size: 15px; }}
}}
"""
    )
