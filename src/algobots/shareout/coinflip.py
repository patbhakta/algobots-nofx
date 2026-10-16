"""Build the standalone coinflip share-out report from the preserved Kalshi archive.

The archive (``research/laya-kalshi/coinflip.jsonl``) records, per settled
KXBTC15M market, the coin's random probability ``p``, the settled ``outcome``
and whether the coin's pick was a ``hit``. It records no price, stake, fee,
fill or P&L. This module therefore keeps two things strictly apart:

* **Observations** — counts, hit rate and the comparison against a 50% coin.
* **Illustrative payoff models** — what an assumed flat $1 bet would have
  returned. These are labelled as assumptions everywhere they appear and are
  never presented as recorded P&L.

Stdlib only, deterministic output (no timestamps), so a rebuild from the same
inputs is byte-identical and can be checked by hash.

    python -m algobots.shareout.coinflip \
        --data data/research/laya-kalshi/coinflip.jsonl \
        --markets data/research/laya-kalshi/coinflip_markets.json \
        --out share-out/
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

MONTHS = {m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), 1)}


@dataclass(frozen=True)
class PayoffModel:
    """Net result of an assumed $1 bet: ``win`` on a hit, ``-loss`` on a miss."""

    key: str
    label: str
    win: float
    loss: float
    note: str

    def pnl(self, hit: bool) -> float:
        return self.win if hit else -self.loss

    @property
    def breakeven(self) -> float:
        """Hit rate at which the expected result is exactly zero."""
        return self.loss / (self.win + self.loss)


EVEN_MONEY = PayoffModel(
    "even",
    "Model A: even money, no fees",
    1.00,
    1.00,
    "Risk $1 to win $1 — what a contract bought at 50¢ pays, before any fee.",
)
FEE_9PCT = PayoffModel(
    "fee",
    "Model B: older 9% fee assumption",
    0.91,
    1.00,
    "Same bet, but 9¢ of every $1 win goes to fees (the Oct 14 draft's "
    "assumption; not Kalshi's published fee schedule).",
)
MODELS = (EVEN_MONEY, FEE_9PCT)


@dataclass(frozen=True)
class Row:
    event: str
    p: float
    outcome: int
    hit: bool
    ts: float

    @property
    def pick(self) -> str:
        return "YES" if self.p >= 0.5 else "NO"

    @property
    def logged(self) -> datetime:
        return datetime.fromtimestamp(self.ts, UTC)


def load_rows(path: Path) -> list[Row]:
    """Load the archive and fail closed if any row contradicts the pick rule."""
    rows: list[Row] = []
    seen: set[str] = set()
    for n, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        row = Row(
            str(raw["event"]),
            float(raw["p"]),
            int(raw["outcome"]),
            bool(raw["hit"]),
            float(raw["ts"]),
        )
        if row.outcome not in (0, 1):
            raise ValueError(f"{path}:{n}: outcome must be 0 or 1")
        if row.hit != ((row.pick == "YES") == (row.outcome == 1)):
            raise ValueError(f"{path}:{n}: hit flag disagrees with pick/outcome")
        if row.event in seen:
            raise ValueError(f"{path}:{n}: duplicate event {row.event}")
        seen.add(row.event)
        if "pnl" in raw or "price" in raw or "fee" in raw:
            raise ValueError(
                f"{path}:{n}: archive now records money fields; "
                "update the report instead of ignoring them"
            )
        rows.append(row)
    if not rows:
        raise ValueError(f"{path}: no rows")
    return rows


def load_markets(path: Path | None, rows: list[Row]) -> dict[str, dict]:
    """Optional market metadata (strike, result); results must match the archive."""
    if path is None:
        return {}
    by_event = {m["event"]: m for m in json.loads(path.read_text())}
    for r in rows:
        m = by_event.get(r.event)
        if m and m.get("result") in ("yes", "no"):
            if (m["result"] == "yes") != (r.outcome == 1):
                raise ValueError(f"{r.event}: market result disagrees with archive")
    return by_event


def close_dt(event: str) -> datetime | None:
    """Ticker suffix ``26SEP181245`` = 2026-09-18 12:45 America/New_York close."""
    code = event.rsplit("-", 1)[-1]
    if len(code) != 11 or code[2:5] not in MONTHS:
        return None
    return datetime(
        2000 + int(code[:2]),
        MONTHS[code[2:5]],
        int(code[5:7]),
        int(code[7:9]),
        int(code[9:11]),
        tzinfo=ZoneInfo("America/New_York"),
    )


def close_time(event: str) -> str:
    """``KXBTC15M-26SEP181245`` closes Sep 18 2026, 12:45 PM New York time."""
    code = event.rsplit("-", 1)[-1]
    mon, day, hh, mm = code[2:5], code[5:7], int(code[7:9]), code[9:11]
    if mon not in MONTHS:
        return code
    return f"{mon.title()} {int(day)} {hh}:{mm} ET"


def equity(rows: list[Row], model: PayoffModel) -> list[float]:
    level, out = 0.0, []
    for r in rows:
        level += model.pnl(r.hit)
        out.append(round(level, 10))
    return out


def binom_two_sided(k: int, n: int) -> float:
    """Exact two-sided binomial p-value against a fair coin."""
    pmf = [math.comb(n, i) / 2**n for i in range(n + 1)]
    return min(1.0, sum(x for x in pmf if x <= pmf[k] * (1 + 1e-9)))


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def bets_to_detect(p1: float, p0: float = 0.5, za: float = 1.96, zb: float = 0.8416) -> int:
    """Bets needed to tell hit rate ``p1`` from ``p0`` (5% two-sided, 80% power)."""
    num = za * math.sqrt(p0 * (1 - p0)) + zb * math.sqrt(p1 * (1 - p1))
    return math.ceil((num / (p1 - p0)) ** 2)


def streaks(rows: list[Row]) -> dict[bool, tuple[int, int]]:
    """Longest run of hits / misses as (length, start index)."""
    best = {True: (0, 0), False: (0, 0)}
    start = 0
    for i, r in enumerate(rows):
        if i and r.hit != rows[i - 1].hit:
            start = i
        length = i - start + 1
        if length > best[r.hit][0]:
            best[r.hit] = (length, start)
    return best


def money(x: float) -> str:
    x = round(x, 2) + 0.0  # no "-0.00"
    return f"{'−' if x < 0 else '+'}${abs(x):,.2f}"


# --------------------------------------------------------------------------- SVG


def equity_svg(rows: list[Row]) -> str:
    """Two illustrative equity lines with a fair-coin 95% band for Model A."""
    curves = {m.key: [0.0] + equity(rows, m) for m in MODELS}
    n = len(rows)
    band = [1.96 * math.sqrt(i) for i in range(n + 1)]
    lo = min(min(min(c) for c in curves.values()), -band[-1]) - 1
    hi = max(max(max(c) for c in curves.values()), band[-1]) + 1
    W, H, L, R, T, B = 820, 330, 52, 150, 16, 40
    pw, ph = W - L - R, H - T - B

    def x(i: float) -> float:
        return L + pw * i / n

    def y(v: float) -> float:
        return T + ph * (hi - v) / (hi - lo)

    def path(vals: list[float]) -> str:
        return " ".join(
            f"{'M' if i == 0 else 'L'}{x(i):.1f},{y(v):.1f}" for i, v in enumerate(vals)
        )

    out = [
        f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="eq-t eq-d" '
        'class="chart" xmlns="http://www.w3.org/2000/svg">',
        '<title id="eq-t">Illustrative cumulative equity, flat $1 bets</title>',
        f'<desc id="eq-d">Model A ends at {money(curves["even"][-1])}, '
        f"Model B ends at {money(curves['fee'][-1])} after {n} bets. "
        "Neither is recorded P&amp;L.</desc>",
    ]
    step = 5 if hi - lo <= 30 else 10
    v = math.ceil(lo / step) * step
    while v <= hi:
        cls = "zero" if v == 0 else "grid"
        out.append(
            f'<line class="{cls}" x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" '
            f'y2="{y(v):.1f}"/><text class="ax" x="{L - 8}" y="{y(v) + 4:.1f}" '
            f'text-anchor="end">{money(v).replace(".00", "")}</text>'
        )
        v += step
    for i in range(0, n + 1, 10):
        out.append(
            f'<text class="ax" x="{x(i):.1f}" y="{T + ph + 18}" text-anchor="middle">{i}</text>'
        )
    out.append(
        f'<text class="ax" x="{L + pw / 2}" y="{H - 4}" text-anchor="middle">'
        "bet number (oldest → newest)</text>"
    )
    upper = " ".join(f"L{x(i):.1f},{y(b):.1f}" for i, b in enumerate(band))
    lower = " ".join(f"L{x(i):.1f},{y(-b):.1f}" for i, b in reversed(list(enumerate(band))))
    out.append(f'<path class="band" d="M{x(0):.1f},{y(0):.1f} {upper} {lower} Z"/>')
    out.append(
        f'<text class="bandlbl" x="{x(n) - 4:.1f}" y="{y(band[-1]) - 6:.1f}" '
        'text-anchor="end">95% of fair-coin paths (Model A) stay in this band</text>'
    )
    for m, cls in ((EVEN_MONEY, "s1"), (FEE_9PCT, "s2")):
        c = curves[m.key]
        out.append(f'<path class="line {cls}" d="{path(c)}"/>')
        out.append(f'<circle class="dot {cls}" cx="{x(n):.1f}" cy="{y(c[-1]):.1f}" r="4"/>')
    ya, yb = y(curves["even"][-1]), y(curves["fee"][-1])
    if abs(ya - yb) < 16:
        ya, yb = ya - 8, yb + 8
    out.append(
        f'<text class="lbl" x="{x(n) + 10:.1f}" y="{ya + 4:.1f}">'
        f"A {money(curves['even'][-1])}</text>"
    )
    out.append(
        f'<text class="lbl" x="{x(n) + 10:.1f}" y="{yb + 4:.1f}">'
        f"B {money(curves['fee'][-1])}</text>"
    )
    # hover targets: one invisible column per bet, native tooltip
    for i, r in enumerate(rows, 1):
        tip = (
            f"Bet {i}: {r.event} · coin said {r.pick} · "
            f"{'HIT' if r.hit else 'MISS'} · A {money(curves['even'][i])} · "
            f"B {money(curves['fee'][i])}"
        )
        out.append(
            f'<rect class="hit" x="{x(i - 0.5):.1f}" y="{T}" width="{pw / n:.1f}" '
            f'height="{ph}"><title>{html.escape(tip)}</title></rect>'
        )
    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------- HTML

CSS = """:root{color-scheme:dark;--s1:#3987e5;--s2:#d95926;--ink:#c9d1d9;--mute:#8b949e}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:ui-monospace,Menlo,Consolas,monospace;background:#0d1117;color:var(--ink);
padding:2rem;line-height:1.55}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:1.35rem;color:#58a6ff;margin-bottom:.25rem}
h2{font-size:1rem;color:#58a6ff;margin:2rem 0 .6rem}
p,li{font-size:.86rem;margin-bottom:.6rem} ul{padding-left:1.2rem}
p.sub{color:var(--mute);font-size:.82rem;margin-bottom:1.25rem}
.stats{display:flex;gap:.8rem;flex-wrap:wrap;margin-bottom:1.25rem}
.stat{background:#161b22;border:1px solid #30363d;border-radius:8px;padding:.7rem 1.1rem;
text-align:center;min-width:120px}
.stat b{display:block;font-size:1.35rem;color:#f0f6fc} .stat span{color:var(--mute);font-size:.7rem}
.callout{background:#161b22;border-left:3px solid #d29922;padding:.8rem 1rem;margin:1rem 0;
border-radius:4px}
table{width:100%;border-collapse:collapse;font-size:.78rem;margin:.5rem 0 1rem}
th,td{padding:.42rem .55rem;border-bottom:1px solid #21262d;text-align:left}
th{color:var(--mute);text-transform:uppercase;font-size:.64rem;letter-spacing:.08em}
td.n,th.n{text-align:right} td.h{color:#3fb950} td.m{color:#f85149} td.na{color:var(--mute)}
code{background:#161b22;padding:.05rem .3rem;border-radius:3px;font-size:.8rem}
.chart{width:100%;height:auto;background:#0d1117}
.chart .grid{stroke:#21262d;stroke-width:1} .chart .zero{stroke:#6e7681;stroke-width:1}
.chart .ax{fill:var(--mute);font-size:11px} .chart .lbl{fill:var(--ink);font-size:12px}
.chart .band{fill:#8b949e;opacity:.12} .chart .bandlbl{fill:var(--mute);font-size:10.5px}
.chart .line{fill:none;stroke-width:2;stroke-linejoin:round}
.chart .s1{stroke:var(--s1)} .chart .s2{stroke:var(--s2);stroke-dasharray:6 4}
.chart .dot{stroke:#0d1117;stroke-width:2} .chart circle.s1{fill:var(--s1)}
.chart circle.s2{fill:var(--s2)}
.chart .hit{fill:transparent} .chart .hit:hover{fill:#ffffff10}
.legend{display:flex;gap:1.5rem;font-size:.78rem;color:var(--ink);margin:.3rem 0 .5rem}
.sw{display:inline-block;width:22px;height:0;border-top:2px solid;vertical-align:middle;
margin-right:.4rem} .sw.s1{border-color:var(--s1)} .sw.s2{border-color:var(--s2);
border-top-style:dashed}
footer{margin-top:2rem;color:#6e7681;font-size:.7rem}"""


@dataclass(frozen=True)
class Summary:
    n: int
    hits: int
    rate: float
    p_value: float
    ci: tuple[float, float]
    ends: dict[str, float]
    up: int
    yes_picks: int

    @property
    def landing_line(self) -> str:
        return (
            f"{self.n} settled predictions · {self.hits} hits ({self.rate:.1%}), "
            "the same as a coin · no P&amp;L was recorded — illustrative payoff "
            "models inside"
        )


def summarise(rows: list[Row]) -> Summary:
    n, hits = len(rows), sum(r.hit for r in rows)
    return Summary(
        n,
        hits,
        hits / n,
        binom_two_sided(hits, n),
        wilson(hits, n),
        {m.key: equity(rows, m)[-1] for m in MODELS},
        sum(r.outcome for r in rows),
        sum(r.pick == "YES" for r in rows),
    )


def render_report(rows: list[Row], markets: dict[str, dict], source_sha: str) -> str:
    s = summarise(rows)
    lo, hi = s.ci
    need = bets_to_detect(FEE_9PCT.breakeven)
    by_p = Counter((r.p, r.hit) for r in rows)
    ps = sorted({r.p for r in rows})
    first, last = rows[0].logged, rows[-1].logged
    st = streaks(rows)
    hit_ex = next(r for r in rows if r.hit and r.p >= 0.6)
    miss_ex = next(r for r in rows if not r.hit and r.p >= 0.6)
    cut_ex = next(r for r in rows if r.p == 0.5)
    eq = {m.key: equity(rows, m) for m in MODELS}
    e = html.escape
    inside = all(abs(v) <= 1.96 * math.sqrt(i) + 1e-9 for i, v in enumerate(eq["even"], 1))
    band_note = (
        "the coin's Model A line stays inside it the whole way"
        if inside
        else "the coin's Model A line leaves it at least once"
    )
    late = sum(1 for r in rows if (c := close_dt(r.event)) and r.logged > c)
    priced = sum(1 for r in rows if r.event in markets)

    def example(r: Row) -> str:
        m = markets.get(r.event, {})
        strike = m.get("floor_strike")
        target = (
            f"BTC had to finish above ${strike:,.2f} for YES"
            if strike
            else "strike not in the preserved metadata"
        )
        went = (
            "finished above the target (settled YES)"
            if r.outcome
            else "did not finish above the target (settled NO)"
        )
        return (
            f"<li><b>{e(r.event)}</b> (closed {close_time(r.event)}; {target}). "
            f"The coin drew <code>p = {r.p:.1f}</code>, so it said <b>{r.pick}</b>. "
            f"BTC {went} → <b>{'HIT' if r.hit else 'MISS'}</b>. "
            "Nothing about bitcoin went into that pick.</li>"
        )

    p_rows = "".join(
        f"<tr><td>{p:.1f}</td><td>{'YES' if p >= 0.5 else 'NO'}</td>"
        f"<td class=n>{by_p[(p, True)] + by_p[(p, False)]}</td>"
        f"<td class=n>{by_p[(p, True)]}</td>"
        f"<td class=n>{by_p[(p, True)] / (by_p[(p, True)] + by_p[(p, False)]):.0%}</td></tr>"
        for p in ps
    )

    table = []
    for i, r in enumerate(rows):
        table.append(
            f"<tr><td class=n>{i + 1}</td><td>{e(r.event)}</td><td>{close_time(r.event)}</td>"
            f"<td>{r.logged:%m-%d %H:%M}</td><td class=n>{r.p:.1f}</td><td>{r.pick}</td>"
            f"<td>{'YES' if r.outcome else 'NO'}</td>"
            f"<td class={'h' if r.hit else 'm'}>{'HIT' if r.hit else 'MISS'}</td>"
            f"<td class=na>not recorded</td>"
            f"<td class=n>{money(eq['even'][i])}</td><td class=n>{money(eq['fee'][i])}</td></tr>"
        )

    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Coinflip Baseline — Kalshi BTC 15m</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<h1>Coinflip Baseline</h1>
<p class="sub">Kalshi “Will BTC be up in 15 minutes?” markets, called by a coin.
Paper evidence only — no orders were placed and no money moved.</p>

<div class="stats">
<div class="stat"><b>{s.n}</b><span>settled markets</span></div>
<div class="stat"><b>{s.hits}</b><span>coin was right</span></div>
<div class="stat"><b>{s.rate:.1%}</b><span>hit rate</span></div>
<div class="stat"><b>{s.n / 2:g}</b><span>a fair coin expects</span></div>
<div class="stat"><b>none</b><span>recorded P&amp;L</span></div>
</div>

<h2>The short version</h2>
<p>We let a coin call {s.n} bitcoin markets. It was right {s.hits} times —
<b>{s.rate:.1%}, exactly what a coin should do</b>. That is the point of this page:
it is the baseline every real strategy has to beat before it is trusted with money.</p>
<p><b>This page does not show a profit or a loss.</b> The archive kept which way the
coin called and how each market settled, but not the price of each bet or any fees.
Without those, the dollar result is unknown. The chart below shows what two
<i>assumed</i> ways of betting would have returned. They are labelled as models, not
results.</p>

<h2>Equity curve — illustrative, flat $1 per bet</h2>
<div class="legend"><span><i class="sw s1"></i>{e(EVEN_MONEY.label)}</span>
<span><i class="sw s2"></i>{e(FEE_9PCT.label)}</span></div>
{equity_svg(rows)}
<p>Each bet adds the model's win amount on a hit and subtracts $1 on a miss. The grey
band is where 95% of truly random runs of Model A would sit; {band_note}.
Hover the chart for each bet.</p>

<h2>Which P&amp;L numbers exist, and which don't</h2>
<table><tr><th>Basis</th><th>What it is</th><th class=n>Result</th></tr>
<tr><td>Recorded</td><td>The archive's fields are <code>event</code>, <code>p</code>,
<code>outcome</code>, <code>hit</code>, <code>ts</code>. No price, stake, fill, fee or P&amp;L
was stored for any of the {s.n} rows. The preserved market metadata covers {priced} of the
{s.n} markets and every price field in it is empty.</td>
<td class="n na">not recorded</td></tr>
<tr><td>{e(EVEN_MONEY.label)}</td><td>{e(EVEN_MONEY.note)} Formula:
{s.hits} × $1.00 − {s.n - s.hits} × $1.00.</td><td class=n>{money(s.ends["even"])}</td></tr>
<tr><td>{e(FEE_9PCT.label)}</td><td>{e(FEE_9PCT.note)} Formula:
{s.hits} × $0.91 − {s.n - s.hits} × $1.00.</td><td class=n>{money(s.ends["fee"])}</td></tr>
</table>
<div class="callout"><b>Correction to the previous version of this page.</b> It showed
“$+0.00” in every row and as the total. Those were placeholders, not observations:
there were no money fields to add up. A $0.00 total is only what Model A gives when hits
and misses are tied — it does not mean the coin broke even. The earlier draft's
<b>{money(s.ends["fee"])}</b> is Model B; it is reproduced above with its formula and is
equally an assumption, not a measured loss.</div>

<h2>Is {s.rate:.1%} good? Compared with 50%</h2>
<ul>
<li>A fair coin expects {s.n / 2:g} hits out of {s.n}. The coin got {s.hits}. The chance of a
result at least this far from 50% by pure luck is <b>p = {s.p_value:.2f}</b> — in other
words, nothing unusual happened.</li>
<li>With only {s.n} bets the honest range for the coin's “true” hit rate is
<b>{lo:.0%} to {hi:.0%}</b> (95% Wilson interval). That range includes both clearly
losing and clearly winning strategies, so {s.n} bets cannot tell them apart.</li>
<li><b>Hit rate alone cannot show profit.</b> Profit depends on the price paid and the
fees. Before fees, buying YES at 80¢ needs better than 80% hits to profit; buying at 30¢
needs only 30%.
Under Model B's fee the break-even hit rate is
<b>{FEE_9PCT.breakeven:.1%}</b>, and telling {FEE_9PCT.breakeven:.1%} apart from 50% reliably
takes roughly <b>{need:,} bets</b> — about {need / s.n:.0f}× this sample.</li>
</ul>

<h2>How the coin chose</h2>
<p>For each market the coin drew a random number <code>p</code> from
{", ".join(f"{p:.1f}" for p in ps)}. If <code>p</code> was 0.5 or higher it said YES
(“BTC up”), otherwise NO. The number looks like a confidence but is just the coin's draw —
the 0.7 calls were no more informed than the 0.3 calls:</p>
<table><tr><th>p</th><th>pick</th><th class=n>calls</th><th class=n>hits</th>
<th class=n>hit rate</th></tr>{p_rows}</table>
<p>It said YES {s.yes_picks} times and NO {s.n - s.yes_picks} times. Bitcoin actually went up
in {s.up} of the {s.n} windows.</p>

<h2>A few real calls</h2>
<ul>
{example(hit_ex)}
{example(miss_ex)}
{example(cut_ex)}
<li>Luck comes in streaks: the longest run of hits was <b>{st[True][0]}</b> in a row
(bets {st[True][1] + 1}–{st[True][1] + st[True][0]}) and the longest run of misses was
<b>{st[False][0]}</b> (bets {st[False][1] + 1}–{st[False][1] + st[False][0]}). A real
strategy has to be judged over enough bets that streaks like these wash out.</li>
</ul>

<h2>How this data was made</h2>
<p>The coin's calls were logged in hourly batches between {first:%b %d %H:%M} and
{last:%b %d %H:%M} UTC. {late} of the {s.n} calls were logged after their market had
already closed (by the ticker's close time). That makes
this a replay, not live trading. It is harmless for a coin, which looks at nothing — but a
real strategy tested this way would be cheating, so ours must be logged before the market
closes.</p>

<h2>Every call</h2>
<table><tr><th class=n>#</th><th>market</th><th>closed</th><th>logged (UTC)</th>
<th class=n>p</th><th>pick</th><th>settled</th><th>result</th><th>recorded P&amp;L</th>
<th class=n>model A cum.</th><th class=n>model B cum.</th></tr>
{"".join(table)}
</table>

<footer>Source: research/laya-kalshi/coinflip.jsonl ({s.n} rows, sha256
{source_sha[:16]}…). Built by <code>python -m algobots.shareout.coinflip</code>
(algobots repo, docs/shareout/coinflip.md). Paper evidence only. Not financial advice.
</footer>
</div></body></html>
"""


def render_index(rows: list[Row]) -> str:
    s = summarise(rows)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AlgoBots — Strategy Reports</title>
<style>
  :root {{ color-scheme: dark; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
     background: #0d1117; color: #c9d1d9; min-height: 100vh; display: flex;
     flex-direction: column; align-items: center; justify-content: center; padding: 2rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 12px;
     padding: 2.5rem 3rem; max-width: 560px; width: 100%; text-align: center; }}
  h1 {{ font-size: 1.5rem; color: #58a6ff; margin-bottom: .5rem; letter-spacing: .05em; }}
  p.sub {{ color: #8b949e; font-size: .85rem; margin-bottom: 2rem; }}
  a.report {{ display: block; background: #21262d; border: 1px solid #30363d;
     border-radius: 8px; padding: 1rem 1.5rem; margin: .75rem 0; text-decoration: none;
     color: #c9d1d9; font-size: .95rem; transition: border-color .15s; }}
  a.report:hover {{ border-color: #58a6ff; color: #58a6ff; }}
  a.report small {{ display: block; color: #8b949e; margin-top: .25rem; font-size: .75rem; }}
  footer {{ margin-top: 2rem; color: #484f58; font-size: .7rem; }}
</style>
</head>
<body>
  <div class="card">
    <h1>AlgoBots</h1>
    <p class="sub">Strategy reports — private, friends &amp; family</p>
    <a class="report" href="coinflip.html">
      🪙 Coinflip Baseline — Kalshi BTC 15m
      <small>{s.landing_line}</small>
    </a>
    <footer>Paper trading only. Not financial advice.</footer>
  </div>
</body>
</html>
"""


def build(data: Path, markets: Path | None, out: Path) -> dict[str, str]:
    rows = load_rows(data)
    meta = load_markets(markets, rows)
    sha = hashlib.sha256(data.read_bytes()).hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    pages = {"coinflip.html": render_report(rows, meta, sha), "index.html": render_index(rows)}
    hashes = {}
    for name, body in pages.items():
        (out / name).write_text(body)
        hashes[name] = hashlib.sha256(body.encode()).hexdigest()
    return hashes


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, required=True)
    ap.add_argument("--markets", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    for name, digest in build(args.data, args.markets, args.out).items():
        print(f"{digest}  {args.out / name}")


if __name__ == "__main__":
    main()
