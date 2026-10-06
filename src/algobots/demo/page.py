# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""One-page live paper-trading dashboard, rendered with the A09 design system."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from algobots.dashboard.design import components as c
from algobots.dashboard.design.css import stylesheet
from algobots.dashboard.design.storyboard import _SCRIPT
from algobots.demo import ledger as L

INTERVAL_S = 15 * 60
STALE_AFTER_S = 25 * 60  # one missed observer run plus slack
SERIES = {  # strategy -> (stroke var, dash) — dash + direct label, never colour alone
    "laya": ("var(--c-ink)", ""),
    "jev": ("var(--c-attention)", "6 4"),
    "coin": ("var(--c-muted)", "2 3"),
}
ACCOUNT = {"id": "pat-kalshi-paper", "label": "Pat · Kalshi paper", "environment": "PAPER"}
TAG = "PAPER · SIMULATED FILLS"


def _usd(x: Decimal) -> dict:
    return {"amount": str(Decimal(x).quantize(L.CENT)), "currency": "USD"}


def _t(ts: float | None, fmt: str = "%H:%M") -> str:
    return datetime.fromtimestamp(ts, UTC).strftime(fmt) + "Z" if ts else "—"


def _age(seconds: float) -> str:
    s = int(seconds)
    return f"{s}s ago" if s < 90 else f"{s // 60}m ago" if s < 5400 else f"{s // 3600}h ago"


def _pctx(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _header(lg: L.Ledger, now: float) -> str:
    last = lg.last_ts
    if last is None:
        feed = c.status("disconnected", "Laya feed: no data")
    else:
        age = now - last
        feed = c.status("connected" if age < STALE_AFTER_S else "stale", f"Laya feed {_age(age)}")
    nxt = f"next decision ≈ {_t(last + INTERVAL_S)}" if last else ""
    kill = (
        c.status("BLOCKED", "kill switch ENGAGED")
        if lg.kill.get("engaged")
        else c.status("ready", "kill switch armed · trading")
    )
    return (
        '<header class="app-header">'
        '<span class="crumb wide">AlgoBots</span><span class="wide" aria-hidden="true">→</span>'
        f'<span class="crumb">{c.e(ACCOUNT["label"])}</span>{c.env_badge("PAPER")}'
        '<span class="meta wide">Kalshi KXBTC15M · USD</span>'
        f'{feed}<span class="meta">{c.e(nxt)}</span>{kill}</header>'
    )


def _banner(start: str, now: float) -> str:
    return (
        '<div class="demo-banner" role="note"><strong>PAPER TRADING</strong>'
        f"<span>since {c.e(start)} · $5–15 per trade</span>"
        "<span>simulated fills at assumed 50¢ mid + Kalshi taker fee · no broker orders</span>"
        f'<span class="meta wide">as of {_t(now, "%Y-%m-%d %H:%M")} · refreshes every 60s</span></div>'
    )


def _strip(lg: L.Ledger, now: float) -> str:
    books = lg.books.values()
    equity = sum((b.equity for b in books), Decimal(0))
    start = sum((b.allocated for b in books), Decimal(0))
    pnl = equity - start
    today = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    today_fills = [d for b in books for d in b.fills if L._day(d.ts) == today]
    blocked = sum(1 for b in books for d in b.decisions if d.status == "BLOCKED")
    ret = f"{pnl / start * 100:.2f}"
    cells = [
        c.metric(
            "Account equity",
            c.money(_usd(equity)),
            f"3 sleeves × {L.SLEEVE} USD"
            + (f" + {start - L.SLEEVE * len(lg.books)} refilled" if lg.refill_ts else ""),
        ),
        c.metric("Net P&L", c.money(_usd(pnl), signed=True), "since open · net of fees"),
        c.metric("Return", c.pct(ret, signed=True), "on capital allocated"),
        c.metric(
            "Fees paid", c.money(_usd(sum((b.fees for b in books), Decimal(0)))), "Kalshi taker"
        ),
        c.metric("Fills today", f'<span class="num">{len(today_fills)}</span>', f"{today} UTC"),
        c.metric("Risk blocks", f'<span class="num">{blocked}</span>', "entries stopped by rails"),
        c.metric("Open exposure", c.money(_usd(Decimal(0))), "every contract settles in 15m"),
    ]
    return f'<section class="strip" aria-label="Account metrics" data-financial="true">{"".join(cells)}</section>'


def _performance(lg: L.Ledger) -> str:
    rows = []
    for b in lg.books.values():
        blocked = sum(1 for d in b.decisions if d.status == "BLOCKED")
        abstain = sum(1 for d in b.decisions if d.status == "ABSTAIN")
        sh = L.sharpe_like(b)
        rows.append(
            [
                f"<strong>{c.e(b.name)}</strong>",
                c.money(_usd(b.equity)),
                c.money(_usd(b.pnl), signed=True),
                f'<span class="num">{len(b.fills)}</span>',
                f'<span class="num">{_pctx(L.hit_rate(b))}</span>',
                c.money(_usd(b.fees)),
                c.money(_usd(b.max_drawdown), signed=True),
                f'<span class="num">{"—" if sh is None else f"{sh:+.3f}"}</span>',
                f'<span class="num">{blocked} / {abstain}</span>',
            ]
        )
    brier = L.brier(lg.rows)
    note = (
        f'<p class="meta">Laya calibrated Brier {brier:.4f} over {len(lg.rows)} intervals vs coin 0.2500 '
        f"(lower is better). Break-even hit rate at 50¢ after fees ≈ 51.8%. "
        f"Mean/σ = mean ÷ standard deviation of per-fill net P&L (unitless, not annualized).</p>"
        if brier is not None
        else ""
    )
    halted = [b.name for b in lg.books.values() if b.exhausted]
    if halted:
        note = (
            f'<p class="halt-note"><strong>Stopped by risk rails:</strong> {c.e(", ".join(halted))} '
            "lost their sleeve and can no longer afford the $5 minimum stake. This is the result, "
            "not an outage: every 15m interval is still decided and logged below with a reason.</p>"
        ) + note
    return (
        c.table(
            [
                "Strategy",
                "Equity",
                "Net P&L",
                "Fills",
                "Hit rate",
                "Fees",
                "Max DD",
                "Mean/σ",
                "Blocked / abst.",
            ],
            rows,
            numeric={1, 2, 3, 4, 5, 6, 7, 8},
            stack=True,
        )
        + note
    )


def _spread(targets: dict[str, float], gap: float, top: float, bottom: float) -> dict[str, float]:
    """Move label baselines apart so none sit closer than ``gap``, keeping all in [top, bottom]."""
    keys = sorted(targets, key=targets.get)
    ys = [targets[k] for k in keys]
    for i in range(len(ys)):
        ys[i] = max(ys[i], top + i * gap, ys[i - 1] + gap if i else top)
    for i in reversed(range(len(ys))):
        ys[i] = min(
            ys[i], bottom - (len(ys) - 1 - i) * gap, ys[i + 1] - gap if i + 1 < len(ys) else bottom
        )
    return dict(zip(keys, ys, strict=True))


def _svg(lg: L.Ledger, W: int, H: int, LBL: int, fs: int, cls: str) -> str:
    pts = [(ts, eq) for b in lg.books.values() for ts, eq in b.curve]
    t0, t1 = min(p[0] for p in pts), max(p[0] for p in pts)
    lo = min(min(float(p[1]) for p in pts), float(L.SLEEVE))
    hi = max(max(float(p[1]) for p in pts), float(L.SLEEVE))
    PAD = 8
    span_t, span_v = (t1 - t0) or 1, (hi - lo) or 1

    def x(ts: float) -> float:
        return PAD + (ts - t0) / span_t * (W - LBL - PAD)

    def y(v: float) -> float:
        return PAD + (hi - v) / span_v * (H - 2 * PAD)

    base = y(float(L.SLEEVE))
    parts = [
        f'<line x1="{PAD}" x2="{W - LBL}" y1="{base:.1f}" y2="{base:.1f}" stroke="var(--c-rule-faint)" stroke-width="1"/>'
    ]
    for ts in lg.refill_ts:
        if t0 <= ts <= t1:
            parts.append(
                f'<line x1="{x(ts):.1f}" x2="{x(ts):.1f}" y1="{PAD}" y2="{H - PAD}" stroke="var(--c-attention)" stroke-dasharray="3 3"/>'
                f'<text x="{x(ts) + 3:.1f}" y="{PAD + fs}" font-size="{fs - 1}" fill="var(--c-attention)">refill {_t(ts, "%b %d %H:%M")}</text>'
            )
    # end labels and the baseline label share the right gutter; spread them so none overlap
    targets = {k: y(float(b.curve[-1][1])) + fs / 3 for k, b in lg.books.items()}
    targets["_base"] = base + fs / 3
    label_y = _spread(targets, fs + 3, fs, H + 20)
    x_lbl = x(t1) + 6
    parts.append(
        f'<text x="{x_lbl:.1f}" y="{label_y["_base"]:.1f}" font-size="{fs}" fill="var(--c-muted)">start {L.SLEEVE}</text>'
    )
    for key, b in lg.books.items():
        stroke, dash = SERIES[key]
        path = " ".join(f"{x(ts):.1f},{y(float(eq)):.1f}" for ts, eq in [(t0, L.SLEEVE), *b.curve])
        parts.append(
            f'<polyline points="{path}" fill="none" stroke="{stroke}" stroke-width="1.75" '
            f'stroke-dasharray="{dash}" vector-effect="non-scaling-stroke"/>'
            f'<text x="{x_lbl:.1f}" y="{label_y[key]:.1f}" font-size="{fs}" fill="{stroke}">'
            f"{c.e(b.name.split()[0])} {float(b.curve[-1][1]):.0f}</text>"
        )
    label = "; ".join(f"{b.name} ends at {b.equity} USD" for b in lg.books.values())
    return (
        f'<svg class="{cls}" viewBox="0 0 {W} {H + 24}" width="100%" role="img" '
        f'aria-label="{c.e(label)}">{"".join(parts)}</svg>'
    )


def _curve(lg: L.Ledger) -> str:
    pts = [p for b in lg.books.values() for p in b.curve]
    if len(pts) < 2:
        return '<p class="empty">Not enough decisions yet to draw an equity curve.</p>'
    t0, t1 = min(p[0] for p in pts), max(p[0] for p in pts)
    refills = (
        f" · dashed orange line = sleeves refilled to {L.SLEEVE} USD (added capital, not P&L)"
        if lg.refill_ts
        else ""
    )
    return (
        f'<p class="meta">Sleeve equity, USD · {_t(t0, "%b %d %H:%M")} → {_t(t1, "%b %d %H:%M")} · one point per 15m interval{refills}</p>'
        + _svg(lg, 900, 220, 130, 12, "chart-d")
        + _svg(lg, 420, 300, 110, 15, "chart-m")
    )


def _risk(lg: L.Ledger, now: float) -> str:
    kill = lg.kill
    engaged = bool(kill.get("engaged"))
    state = (
        c.status(
            "BLOCKED",
            f"ENGAGED since {_t(kill.get('since_ts'), '%b %d %H:%M')} — all new entries blocked",
        )
        if engaged
        else c.status("ready", "Armed — entries allowed")
    )
    verb, val = ("Release kill switch", "off") if engaged else ("Engage kill switch", "on")
    form = (
        f'<form method="post" action="/demo/kill-switch" class="actions">'
        f'<input type="hidden" name="engaged" value="{val}">'
        '<label class="field"><span class="sr-only">Your name for the audit log</span>'
        '<input name="actor" maxlength="40" placeholder="your name (audit log)" autocomplete="name"></label>'
        f'<button type="submit" class="action" data-account="{ACCOUNT["id"]}" data-environment="PAPER">'
        f'<span>{verb}</span><span class="sr-only">, </span><span class="ctx">{c.e(ACCOUNT["label"])} · PAPER</span></button></form>'
    )
    today = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    cap = L.ENVELOPE.max_daily_loss
    rows = []
    for b in lg.books.values():
        day_pnl = sum((d.pnl for d in b.fills if L._day(d.ts) == today), Decimal(0))
        used = max(Decimal(0), -day_pnl)
        tripped = L.ENVELOPE.check_daily_loss(day_pnl).tripped
        rows.append(
            [
                c.e(b.name),
                c.money(_usd(day_pnl), signed=True),
                c.bar(
                    float(min(Decimal(1), used / cap)), label=f"{used} of {cap} USD daily loss used"
                )
                + f'<span class="meta">{used} / {cap}</span>',
                c.status("BLOCKED", "kill switch — entries blocked")
                if lg.kill.get("engaged")
                else c.status("BLOCKED", "sleeve exhausted — entries blocked")
                if b.exhausted
                else c.status("BLOCKED", "daily cap hit — entries blocked")
                if tripped
                else c.status("ready", "within cap"),
            ]
        )
    caps = (
        f'<p class="meta">Per-strategy <code>RiskEnvelope</code>: max order value {L.ENVELOPE.max_order_value} USD, '
        f"max daily loss {cap} USD (UTC day). Size clamps fired: {len(lg.clamp_events)}.</p>"
    )
    hist = kill.get("history") or []
    last_flip = (
        f'<p class="meta">Last flip: {"engaged" if hist[-1]["engaged"] else "released"} by {c.e(hist[-1]["actor"])} at {_t(hist[-1]["ts"], "%b %d %H:%M")}</p>'
        if hist
        else ""
    )
    return (
        f"<h3>Kill switch</h3><p>{state}</p>{form}{last_flip}"
        f"<h3>Daily-loss envelopes · {today}</h3>"
        + c.table(
            ["Strategy", "P&L today", "Loss cap used", "State"], rows, numeric={1}, stack=True
        )
        + caps
    )


def _decisions(lg: L.Ledger, limit: int = 12) -> str:
    by_event: dict[str, dict] = {}
    for b in lg.books.values():
        for d in b.decisions[-limit:]:
            by_event.setdefault(d.event, {})[d.strategy] = d
    rows_by_event = {r.event: r for r in lg.rows}
    out = []
    for event in sorted(by_event, key=lambda ev: rows_by_event[ev].ts, reverse=True)[:limit]:
        r = rows_by_event[event]
        for key in L.STRATEGIES:
            d = by_event[event].get(key)
            if d is None:
                continue
            first = key == "laya"
            res = ""
            if d.status == "FILLED":
                res = c.money(_usd(d.pnl), signed=True)
            out.append(
                [
                    _t(r.ts) if first else "",
                    (
                        f"{c.e(event.split('-')[-1])}<br><span class='meta'>${r.strike:,.0f} · closed {'UP' if r.outcome else 'DOWN'}</span>"
                    )
                    if first
                    else "",
                    c.e(L.STRATEGIES[key]),
                    c.status(d.status, f"{d.status.lower()} {d.side or ''}".strip()),
                    c.money(_usd(d.stake))
                    if d.status == "FILLED"
                    else '<span class="meta">—</span>',
                    res,
                    f'<span class="meta">{c.e(d.reason)}</span>',
                ]
            )
    return c.table(
        ["Time", "Interval", "Strategy", "Decision", "Stake", "P&L", "Reason"],
        out,
        numeric={4, 5},
        stack=True,
        empty="No decisions yet — the Laya observer writes one per settled 15m interval.",
    )


def _accounts(lg: L.Ledger) -> str:
    rows = [
        [
            c.e(ACCOUNT["label"]) + " / " + c.e(b.name),
            c.env_badge("PAPER"),
            c.money(_usd(b.allocated)),
            c.money(_usd(b.equity)),
            c.money(_usd(b.pnl), signed=True),
            c.status("BLOCKED", "halted — kill switch")
            if lg.kill.get("engaged")
            else c.status("BLOCKED", "halted — sleeve exhausted")
            if b.exhausted
            else c.status("connected", "running"),
        ]
        for b in lg.books.values()
    ]
    return c.table(
        ["Account / deployment", "Mode", "Allocated", "Equity", "Net P&L", "State"],
        rows,
        numeric={2, 3, 4},
        stack=True,
    )


def render(lg: L.Ledger, *, start: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    body = (
        _strip(lg, now)
        + '<div class="cols two">'
        + c.panel("Strategy performance", _performance(lg), financial=True, tag=TAG)
        + c.panel("Risk state", _risk(lg, now), raised=True)
        + "</div>"
        + c.panel("Equity by strategy", _curve(lg), financial=True, tag=TAG)
        + c.panel("Recent decisions and reasons", _decisions(lg), financial=True, tag=TAG)
        + c.panel("Accounts", _accounts(lg), financial=True, tag=TAG)
    )
    title = "AlgoBots — live paper trading"
    return (
        '<!doctype html>\n<html lang="en" data-texture="on" data-motion="on">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="refresh" content="60">\n'
        f"<title>{title}</title>\n<style>\n{stylesheet()}"
        ".panel{margin-bottom:var(--space-4,16px)} .panel h3{font-size:13px;margin:8px 0 4px}"
        " table.data td{vertical-align:top} table.data td:first-child{white-space:nowrap}"
        " .halt-note{margin:8px 0;padding:6px 8px;border-left:3px solid var(--c-attention)}"
        " .actions .field input{margin-right:8px} .chart-m{display:none} .panel .body{overflow-x:auto}"
        " @media (min-width:1101px){.cols.two{grid-template-columns:minmax(0,3fr) minmax(0,2fr)}}"
        " @media (max-width:700px){.chart-d{display:none} .chart-m{display:block}"
        " table.data.stack thead{display:none}"
        " table.data.stack,table.data.stack tbody,table.data.stack tr{display:block;width:100%}"
        " table.data.stack tr{border-bottom:var(--rule);padding:6px 0}"
        " table.data.stack td{display:flex;justify-content:space-between;gap:12px;padding:2px 0;border:0;text-align:right;white-space:normal}"
        " table.data.stack td::before{content:attr(data-label);color:var(--c-muted);text-align:left;flex:none}"
        " table.data.stack td:empty{display:none}"
        " table.data.stack td[data-label=Reason]{display:block;text-align:left}"
        " table.data.stack td[data-label=Reason]::before{display:block}}</style>\n</head>\n<body>\n"
        f'<div class="chrome">{_banner(start, now)}{_header(lg, now)}</div>\n'
        f'<nav class="screens" aria-label="Settings"><span class="meta">Live feed: the Laya observer scores each Kalshi BTC 15m interval as it settles. Each strategy decides from earlier intervals only; fills are simulated, never sent to a broker.</span><span class="spacer"></span>{c.settings()}</nav>\n'
        f'<main id="main" data-screen="demo">\n<h1 class="sr-only">{title}</h1>\n{body}\n</main>\n'
        f"<script>{_SCRIPT}</script>\n</body>\n</html>\n"
    )
