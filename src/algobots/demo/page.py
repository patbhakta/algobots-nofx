# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""One-page live paper-trading terminal: accounts, positions, orders and risk."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal

from algobots.dashboard.design import components as c
from algobots.demo import ledger as L
from algobots.demo.theme import CLOCK, CSS

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
    """Status bar: mode · feed age · next decision · kill switch · UTC clock."""
    last = lg.last_ts
    if last is None:
        feed = c.status("disconnected", "feed: no data")
    else:
        age = now - last
        feed = c.status("connected" if age < STALE_AFTER_S else "stale", f"feed {_age(age)}")
    kill = (
        c.status("BLOCKED", "KILL ENGAGED")
        if lg.kill.get("engaged")
        else c.status("ready", "kill armed")
    )
    return (
        '<header class="statusbar"><span class="brand">ALGOBOTS</span>'
        f"<span>{c.env_badge('PAPER')}</span>"
        f'<span class="wide">{c.e(ACCOUNT["label"])} · KXBTC15M · USD</span>'
        f"<span>{feed}</span>"
        f"<span>next {_t(last + INTERVAL_S) if last else '—'}</span>"
        f'<span>{kill}</span><span class="spacer"></span>'
        f'<span id="utc" class="num">{_t(now, "%H:%M:%S")}</span></header>'
    )


def _banner(start: str) -> str:
    return (
        '<div class="disclosure" role="note"><strong>PAPER TRADING</strong>'
        f"<span>since {c.e(start)} · $5–15/trade</span>"
        "<span>simulated fills at assumed 50¢ mid + Kalshi taker fee · no broker orders</span>"
        '<span class="wide">decides from prior settled intervals only · refresh 60s</span></div>'
    )


def _day_pnl(b: L.StrategyBook, today: str) -> Decimal:
    return sum((d.pnl for d in b.fills if L._day(d.ts) == today), Decimal(0))


def _halt(lg: L.Ledger, b: L.StrategyBook, today: str) -> str | None:
    """Why new entries are blocked right now (None = trading); one answer for every panel."""
    if lg.kill.get("engaged"):
        return "kill switch"
    if b.exhausted:
        return "sleeve exhausted"
    if L.ENVELOPE.check_daily_loss(_day_pnl(b, today)).tripped:
        return "daily cap hit · resumes 00:00Z"
    return None


def _strip(lg: L.Ledger, now: float) -> str:
    books = lg.books.values()
    equity = sum((b.equity for b in books), Decimal(0))
    start = sum((b.allocated for b in books), Decimal(0))
    pnl = equity - start
    today = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    today_fills = [d for b in books for d in b.fills if L._day(d.ts) == today]
    blocked = sum(1 for b in books for d in b.decisions if d.status == "BLOCKED")
    opening = L.SLEEVE * len(lg.books)
    ret = f"{pnl / opening * 100:.2f}"
    cells = [
        c.metric(
            "Account equity",
            c.money(_usd(equity)),
            f"3 sleeves × {L.SLEEVE} USD"
            + (f" + {start - opening} refilled" if lg.refill_ts else ""),
        ),
        c.metric("Net P&L", c.money(_usd(pnl), signed=True), "since open · net of fees"),
        c.metric(
            "Return",
            c.pct(ret, signed=True),
            "on starting capital" + (" · refills excluded" if lg.refill_ts else ""),
        ),
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
        f'<p class="meta">Brier {brier:.4f} (n={len(lg.rows)}) vs coin 0.2500 · '
        "break-even hit 51.8% · Mean/σ = per-fill net P&L, not annualized</p>"
        if brier is not None
        else ""
    )
    halted = [b.name for b in lg.books.values() if b.exhausted]
    if halted:
        note = (
            f'<p class="halt-note"><strong>Stopped by risk rails:</strong> {c.e(", ".join(halted))} '
            "· sleeve below $5 min stake · intervals still decided and logged</p>"
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
                "Blk / abst.",
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
                f'<text x="{x(ts) + (-3 if x(ts) > (W - LBL) / 2 else 3):.1f}" y="{PAD + fs}" font-size="{fs - 1}" '
                f'text-anchor="{"end" if x(ts) > (W - LBL) / 2 else "start"}" fill="var(--c-attention)">refill {_t(ts)}</text>'
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
        day_pnl = _day_pnl(b, today)
        used = max(Decimal(0), -day_pnl)
        halt = _halt(lg, b, today)
        rows.append(
            [
                c.e(b.name),
                c.money(_usd(day_pnl), signed=True),
                c.bar(
                    float(min(Decimal(1), used / cap)), label=f"{used} of {cap} USD daily loss used"
                )
                + f'<span class="meta">{used} / {cap}</span>',
                c.status("BLOCKED", f"{halt} — entries blocked")
                if halt
                else c.status("ready", "within cap"),
            ]
        )
    caps = (
        f'<p class="meta">RiskEnvelope/strategy: max order {L.ENVELOPE.max_order_value} USD · '
        f"max daily loss {cap} USD (UTC) · size clamps {len(lg.clamp_events)}</p>"
    )
    hist = kill.get("history") or []
    last_flip = (
        f'<p class="meta">last flip: {"engaged" if hist[-1]["engaged"] else "released"} by {c.e(hist[-1]["actor"])} at {_t(hist[-1]["ts"], "%b %d %H:%M")}</p>'
        if hist
        else ""
    )
    return (
        f'<h3>Kill switch</h3><div class="risk-head">{state}{form}</div>{last_flip}'
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
                        f"{c.e(event.split('-')[-1])} <span class='meta'>${r.strike:,.0f} {'UP' if r.outcome else 'DN'}</span>"
                    )
                    if first
                    else "",
                    c.e(L.STRATEGIES[key]),
                    c.status(d.status, f"{d.status.lower()} {d.side or ''}".strip()),
                    c.money(_usd(d.stake))
                    if d.status == "FILLED"
                    else '<span class="meta">—</span>',
                    res,
                    f'<span class="meta" title="{c.e(d.reason)}">{c.e(d.reason)}</span>',
                ]
            )
    return c.table(
        ["Time", "Interval", "Strategy", "Decision", "Stake", "P&L", "Reason"],
        out,
        numeric={4, 5},
        stack=True,
        empty="No decisions yet — the Laya observer writes one per settled 15m interval.",
    )


def _accounts(lg: L.Ledger, now: float) -> str:
    today = datetime.fromtimestamp(now, UTC).strftime("%Y-%m-%d")
    rows = [
        [
            c.e(b.name),
            c.env_badge("PAPER"),
            c.money(_usd(b.allocated)),
            c.money(_usd(b.equity)),
            c.money(_usd(b.pnl), signed=True),
            c.status("BLOCKED", f"halted — {halt}") if halt else c.status("connected", "running"),
        ]
        for b in lg.books.values()
        for halt in [_halt(lg, b, today)]
    ]
    return c.table(
        ["Deployment", "Mode", "Allocated", "Equity", "Net P&L", "State"],
        rows,
        numeric={2, 3, 4},
        stack=True,
    )


def render(lg: L.Ledger, *, start: str, now: float | None = None) -> str:
    now = time.time() if now is None else now
    body = (
        _strip(lg, now)
        + '<div class="grid">'
        + c.panel("Accounts", _accounts(lg, now), financial=True, tag=TAG, cls="full")
        + c.panel("Positions · Strategy performance", _performance(lg), financial=True, tag=TAG)
        + c.panel("Risk state", _risk(lg, now))
        + c.panel(
            "Orders · Recent decisions and reasons",
            _decisions(lg),
            financial=True,
            tag=TAG,
            cls="full",
        )
        + c.panel("Equity by strategy", _curve(lg), financial=True, tag=TAG, cls="full")
        + "</div>"
    )
    title = "AlgoBots — live paper trading"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="refresh" content="60">\n'
        f"<title>{title}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f'<div class="chrome">{_header(lg, now)}{_banner(start)}</div>\n'
        f'<main id="main" data-screen="demo">\n<h1 class="sr-only">{title}</h1>\n{body}\n</main>\n'
        f"<script>{CLOCK}</script>\n</body>\n</html>\n"
    )
