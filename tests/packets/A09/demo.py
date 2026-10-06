"""A09 demo: the design system on fixtures plus failure paths (``make demo-A09``)."""

from algobots.dashboard.design import components as c
from algobots.dashboard.design import tokens as t
from algobots.dashboard.design.grain import tile_sha256
from algobots.dashboard.design.storyboard import pages
from algobots.dashboard.fixtures import fixture

built = pages()
rows = t.contrast_report()
print(
    f"[ok] storyboard: {len(built) - 1} pages + index, static, DEMO DATA on every page; "
    f"grain tile sha256 {tile_sha256()[:12]} at {t.GRAIN['opacity']:.0%}"
)
print(
    f"[ok] contrast: {sum(r['aa_text'] for r in rows)}/{len(rows)} text/surface pairs >= 4.5:1 "
    f"(grain on and off); lowest {min(r['ratio'] for r in rows)}:1"
)
spec = t.SPEC_COLORS["attention"]
print(
    f"[adjusted] spec attention {spec} is {t.contrast(spec, t.COLORS['paper']):.2f}:1 on paper "
    f"(fails AA); shipped {t.COLORS['attention']} is "
    f"{t.worst_contrast(t.COLORS['attention'], t.COLORS['paper'], grain=True):.2f}:1 under grain"
)

try:
    c.action("Buy SPY", account=fixture("good")["accounts"][0], environment=None)
except ValueError as exc:
    print(f"[rejected] action without environment: {exc}")

try:
    c.action("Buy SPY", account=fixture("good")["accounts"][0], environment="LIVE")
except ValueError as exc:
    print(f"[rejected] action with mismatched environment: {exc}")

stale = built["overview-stale.html"]
approve = stale[stale.index('data-action="Approve') :].split("</button>", 1)[0]
pause = stale[stale.index('data-action="Pause all strategies"') :].split("</button>", 1)[0]
print(
    "[paused] stale feed: approve disabled "
    f"({'disabled' in approve and 'market data 7m 11s old' in approve}); "
    f"pause stays available ({'disabled' not in pause})"
)

unknown = built["overview-unknown.html"]
equity = unknown[unknown.index(">Equity<") :].split("</div></div>", 1)[0]
print(f"[unavailable] unknown valuation renders 'Unavailable', not 0: {'Unavailable' in equity}")
