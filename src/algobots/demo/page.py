# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Live paper-trading terminal: Accounts / Positions / Orders / Risk / Decision quality.

Selecting an account (``?account=``) sets the context every pane filters to;
``all`` is the aggregate. Data comes from ``demo.blotter`` so the page and
the JSON endpoints share one source.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from algobots.dashboard.design import components as c
from algobots.demo import blotter as B
from algobots.demo import decisions as D
from algobots.demo import ledger as L
from algobots.demo import studio as S
from algobots.demo.theme import CLOCK, CSS, KEYS

INTERVAL_S = 15 * 60
STALE_AFTER_S = 25 * 60  # one missed observer run plus slack
SERIES = {  # strategy -> (stroke var, dash) — dash + direct label, never colour alone
    "laya": ("var(--c-ink)", ""),
    "jev": ("var(--c-attention)", "6 4"),
    "coin": ("var(--c-muted)", "2 3"),
}
ACCOUNT = {"id": "pat-kalshi-paper", "label": "Pat · Kalshi paper", "environment": "PAPER"}
TAG = "PAPER · SIMULATED FILLS"
ORDER_ROWS = 60
NONE = '<span class="meta nil">—</span>'  # hidden in mobile cards'


def _usd(x: Decimal | str) -> dict:
    return {"amount": str(Decimal(x).quantize(L.CENT)), "currency": "USD"}


def _t(ts: float | None, fmt: str = "%H:%M") -> str:
    return datetime.fromtimestamp(ts, UTC).strftime(fmt) + "Z" if ts else "—"


def _age(seconds: float) -> str:
    s = int(seconds)
    return f"{s}s ago" if s < 90 else f"{s // 60}m ago" if s < 5400 else f"{s // 3600}h ago"


def _pctx(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.1f}%"


def _query(account: str, status: str | None = None) -> str:
    q = {k: v for k, v in (("account", account), ("status", status)) if v and v != B.ALL}
    return c.e(f"?{urlencode(q)}") if q else ""  # HTML-escaped: only ever lands in attributes


def _ctx_label(account: str) -> str:
    return "All accounts" if account == B.ALL else L.STRATEGIES[account]


def _header(lg: L.Ledger, now: float, account: str) -> str:
    """Status bar: mode · context · feed age · next decision · kill switch · UTC clock."""
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
        f'<span class="ctxbar" data-account="{account}">ctx <strong>{c.e(_ctx_label(account))}</strong></span>'
        f'<span class="wide">{c.e(ACCOUNT["label"])} · {B.INSTRUMENT} · USD</span>'
        f"<span>{feed}</span>"
        f'<span class="wide">next {_t(last + INTERVAL_S) if last else "—"}</span>'
        f'<span>{kill}</span><span class="spacer"></span>'
        f'<span id="utc" class="num">{_t(now, "%H:%M:%S")}</span></header>'
    )


def _stateline(lg: L.Ledger, now: float, account: str, supervisor_down: bool) -> str:
    """One terminal line: disconnected > empty > live (loading is set client-side on switch)."""
    last, books = lg.last_ts, B.books(lg, account)
    if last is None or now - last >= STALE_AFTER_S:
        state, kind = "disconnected", "disconnected"
        text = "DISCONNECTED · feed " + ("no data" if last is None else f"stale {_age(now - last)}")
    elif supervisor_down:
        state, kind, text = "disconnected", "disconnected", "DISCONNECTED · worker supervisor down"
    elif not any(b.decisions for b in books):
        state, kind, text = "empty", "stale", f"EMPTY · no decisions yet · {_ctx_label(account)}"
    else:
        n = len(books)
        state, kind = "connected", "connected"
        text = f"CONNECTED · {_ctx_label(account)} · {n} account{'s' * (n > 1)} · feed {_age(now - last)}"
    return f'<p class="stateline" id="state" data-state="{state}">{c.status(kind, text)}</p>'


def render_denied(code: int, account: str, why: str) -> str:
    """403/404 for ``?account=``: status bar + one line, no data, no fallback to All."""
    word = "DENIED" if code == 403 else "NOT FOUND"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>AlgoBots — {word.lower()}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        '<div class="chrome"><header class="statusbar"><span class="brand">ALGOBOTS</span>'
        f"<span>{c.env_badge('PAPER')}</span>"
        f'<span class="ctxbar" data-account="{c.e(account)}">ctx <strong>{c.e(account)}</strong></span></header></div>\n'
        f'<main id="main" data-screen="demo" data-state="denied">\n'
        f'<p class="stateline" id="state" data-state="denied">{c.status("BLOCKED", f"{word} · {code} · {why}")}</p>\n'
        '<p><a href="/demo">/demo</a></p>\n</main>\n</body>\n</html>\n'
    )


def _banner(start: str) -> str:
    return (
        '<div class="disclosure" role="note"><strong>PAPER TRADING</strong>'
        f"<span>since {c.e(start)} · $5–15/trade</span>"
        "<span>simulated fills at assumed 50¢ mid + Kalshi taker fee · no broker orders</span>"
        '<span class="wide">decides from prior settled intervals only · refresh 60s · ↑/↓ + Enter selects account</span></div>'
    )


def _strip(lg: L.Ledger, now: float, account: str) -> str:
    books = B.books(lg, account)
    equity = sum((b.equity for b in books), Decimal(0))
    start = sum((b.allocated for b in books), Decimal(0))
    pnl = equity - start
    day = B.today(now)
    today_fills = [d for b in books for d in b.fills if L._day(d.ts) == day]
    blocked = sum(1 for b in books for d in b.decisions if d.status == "BLOCKED")
    opening = L.SLEEVE * len(books)
    ret = f"{pnl / opening * 100:.2f}"
    cells = [
        c.metric(
            "Equity",
            c.money(_usd(equity)),
            f"{len(books)} × {L.SLEEVE} USD sleeve"
            + (f" + {start - opening} refilled" if start > opening else ""),
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
        c.metric("Fills today", f'<span class="num">{len(today_fills)}</span>', f"{day} UTC"),
        c.metric("Risk blocks", f'<span class="num">{blocked}</span>', "entries stopped by rails"),
        c.metric(
            "Open positions",
            f'<span class="num">{len(B.positions(lg, now, account))}</span>',
            "15m contracts",
        ),
    ]
    return f'<section class="strip" aria-label="Account metrics" data-financial="true">{"".join(cells)}</section>'


WORKER_KIND = {  # supervisor state -> status style; exited is an alert (no auto-restart)
    "ready": "connected",
    "starting": "stale",
    "stale": "stale",
    "exited": "BLOCKED",
    "stopped": "disconnected",
    "not_started": "disconnected",
}


def _worker(w: dict | None, now: float) -> str:
    if not w:
        return NONE
    st = w.get("state", "not_started")
    label = f"{st} ({w.get('exit_code')})" if st == "exited" else st.replace("_", " ")
    bits = [f"pid {w['pid']}" if w.get("pid") else ""]
    bits.append(f"{w['rss_mb']:.0f}MB" if w.get("rss_mb") is not None else "")
    bits.append(f"hb {_age(now - w['last_heartbeat'])}" if w.get("last_heartbeat") else "")
    meta = " · ".join(b for b in bits if b)
    return c.status(WORKER_KIND.get(st, "stale"), label.upper()) + (
        f' <span class="meta">{meta}</span>' if meta else ""
    )


def _accounts(lg: L.Ledger, now: float, account: str, workers: dict[str, dict]) -> str:
    """Selectable rows (click, or ↑/↓ + Enter); ``All`` is the aggregate."""
    day = B.today(now)
    heads = ["Account", "Mode", "Allocated", "Equity", "Net P&L", "Today", "State", "Worker"]
    numeric = {2, 3, 4, 5}

    def row(key: str, books: list[L.StrategyBook]) -> str:
        halts = [h for b in books for h in [B.halt(lg, b, day)] if h]
        if key == B.ALL:
            state = (
                c.status("BLOCKED", f"{len(halts)}/{len(books)} HALTED")
                if halts
                else c.status("connected", f"{len(books)} RUNNING")
            )
        else:
            state = (
                c.status("BLOCKED", f"HALT {halts[0].upper()}")
                if halts
                else c.status("connected", "RUNNING")
            )
        cells = [
            f'<a href="/demo{_query(key)}">{c.e(_ctx_label(key))}</a>',
            c.env_badge("PAPER"),
            c.money(_usd(sum((b.allocated for b in books), Decimal(0)))),
            c.money(_usd(sum((b.equity for b in books), Decimal(0)))),
            c.money(_usd(sum((b.pnl for b in books), Decimal(0))), signed=True),
            c.money(_usd(sum((B.day_pnl(b, day) for b in books), Decimal(0))), signed=True),
            state,
            _worker(workers.get(key), now)
            if key != B.ALL
            else (
                f'<span class="meta">{sum(1 for k in lg.books if (workers.get(k) or {}).get("state") == "ready")}'
                f"/{len(lg.books)} ready</span>"
            ),
        ]
        sel = key == account
        tds = "".join(
            f'<td{" class=n" if i in numeric else ""} data-label="{heads[i]}">{v}</td>'
            for i, v in enumerate(cells)
        )
        return (
            f'<tr class="acct{" sel" if sel else ""}" data-account="{key}" '
            f'data-href="/demo{_query(key)}" tabindex="0" aria-selected="{str(sel).lower()}">{tds}</tr>'
        )

    th = "".join(
        f'<th scope="col"{" class=n" if i in numeric else ""}>{h}</th>' for i, h in enumerate(heads)
    )
    body = row(B.ALL, list(lg.books.values())) + "".join(row(k, [b]) for k, b in lg.books.items())
    return (
        '<table class="data stack accounts" role="grid" aria-label="Accounts — select to set context">'
        f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"
    )


def _positions(lg: L.Ledger, now: float, account: str) -> str:
    rows = [
        [
            c.e(L.STRATEGIES[p["account"]]),
            c.e(p["instrument"]),
            c.e(p["side"]),
            f'<span class="num">{p["qty"]}</span>',
            f'<span class="num">{p["avg_price"]}</span>',
            f'<span class="num">{p["mark"]}</span>',
            c.money(_usd(p["unrealized_pnl"]), signed=True),
            f'<span class="num">{p["expires_in_s"] // 60}m{p["expires_in_s"] % 60:02d}s</span>',
        ]
        for p in B.positions(lg, now, account)
    ]
    return c.table(
        ["Account", "Instrument", "Side", "Qty", "Avg px", "Mark", "Unreal. P&L", "Expiry"],
        rows,
        numeric={3, 4, 5, 6, 7},
        stack=True,
        empty="No open positions: every contract has settled (15m expiry). Flat.",
    )


def _orders(lg: L.Ledger, account: str, status: str | None) -> str:
    counts = {s: len(B.orders(lg, account, s, limit=None)) for s in B.STATUSES}
    links = "".join(
        f'<a href="/demo{_query(account, s)}" class="filt{" on" if s == status else ""}"'
        f"{' aria-current=true' if s == status else ''}>"
        f"{s or 'all'} {sum(counts.values()) if s is None else counts[s]}</a>"
        for s in (None, *B.STATUSES)
    )
    json_link = f"/demo/api/orders{_query(account, status)}"
    kind = {"filled": "FILLED", "blocked": "BLOCKED", "abstain": "ABSTAIN"}
    rows = []
    for o in B.orders(lg, account, status, limit=ORDER_ROWS):
        filled = o["status"] == "filled"
        rows.append(
            [
                f'<span class="num" data-order="{c.e(o["id"])}">{_t(o["ts"], "%m-%d %H:%M")}</span>',
                f'<span title="{c.e(o["deployment"])} · artifact {c.e(o["artifact"])}">{c.e(L.STRATEGIES[o["account"]])}</span>',
                c.e(o["instrument"].split("-")[-1]),
                c.e(o["side"] or "—"),
                f'<span class="num">{o["qty"]}</span>' if filled else NONE,
                f'<span class="num">{o["price"]}</span>' if filled else NONE,
                c.money(_usd(o["notional"])) if filled else NONE,
                c.money(_usd(o["fee"])) if filled else NONE,
                c.money(_usd(o["pnl"]), signed=True) if filled else NONE,
                c.status(kind[o["status"]], o["status"] + (" · clamped" if o["clamped"] else "")),
                f'<span class="meta" title="{c.e(o["reason"])}">{c.e(o["reason"])}</span>',
            ]
        )
    return (
        f'<nav class="filters" aria-label="Filter orders by status">{links}'
        f'<span class="meta">newest {ORDER_ROWS} · <a href="{json_link}">JSON</a></span></nav>'
        + c.table(
            [
                "Time",
                "Account",
                "Instr.",
                "Side",
                "Qty",
                "Px",
                "Notional",
                "Fee",
                "Settled",
                "Status",
                "Reason",
            ],
            rows,
            numeric={4, 5, 6, 7, 8},
            stack=True,
            empty="No orders match this account and status.",
        )
    )


def _risk(lg: L.Ledger, now: float, account: str) -> str:
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
        f'<input type="hidden" name="account" value="{account}">'
        '<label class="field"><span class="sr-only">Your name for the audit log</span>'
        '<input name="actor" maxlength="40" placeholder="your name (audit log)" autocomplete="name"></label>'
        f'<button type="submit" class="action" data-account="{ACCOUNT["id"]}" data-environment="PAPER">'
        f'<span>{verb}</span><span class="sr-only">, </span><span class="ctx">{c.e(ACCOUNT["label"])} · PAPER · all accounts</span></button></form>'
    )
    hist = kill.get("history") or []
    last_flip = (
        f'<p class="meta">last flip: {"engaged" if hist[-1]["engaged"] else "released"} by {c.e(hist[-1]["actor"])} at {_t(hist[-1]["ts"], "%b %d %H:%M")}</p>'
        if hist
        else '<p class="meta">last flip: never</p>'
    )
    rows = []
    for r in B.risk(lg, now, account):
        used, cap = Decimal(r["daily_loss_used"]), Decimal(r["max_daily_loss"])
        big, mov = Decimal(r["largest_order_today"]), Decimal(r["max_order_value"])
        eq, floor = Decimal(r["equity"]), Decimal(r["sleeve_floor"])
        rows.append(
            [
                c.e(L.STRATEGIES[r["account"]]),
                c.bar(float(big / mov), label=f"largest order today {big} of {mov} USD")
                + f'<span class="num">{big.quantize(L.CENT)}/{mov}</span>',
                c.bar(
                    float(min(Decimal(1), used / cap)), label=f"{used} of {cap} USD daily loss used"
                )
                + f'<span class="num">{used.quantize(L.CENT)}/{cap}</span>',
                f'<span class="num{" neg" if eq < floor else ""}">{eq.quantize(L.CENT)} ≥ {floor}</span>',
                f'<span class="num">{r["clamps"]}</span>',
                c.status("BLOCKED", f"HALT {r['halt'].upper()}")
                if r["halt"]
                else c.status("ready", "RUNNING"),
            ]
        )
    return (
        f'<h3>Kill switch · all accounts</h3><div class="risk-head">{state}{form}</div>{last_flip}'
        f"<h3>Limits used · {B.today(now)} UTC</h3>"
        + c.table(
            ["Account", "Order value", "Daily loss", "Equity ≥ floor", "Clamps", "State"],
            rows,
            numeric={4},
            stack=True,
        )
        + '<p class="meta">order value = largest fill today / max · floor = min stake + fee · clamps = orders sized down to max order value</p>'
    )


def _performance(lg: L.Ledger, account: str) -> str:
    rows = []
    for b in B.books(lg, account):
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
    brier = L.brier(lg.rows) if "laya" in {b.key for b in B.books(lg, account)} else None
    note = (
        f'<p class="meta">Laya Brier {brier:.4f} (n={len(lg.rows)}) vs coin 0.2500 · '
        "break-even hit 51.8% · Mean/σ = per-fill net P&L, not annualized</p>"
        if brier is not None
        else ""
    )
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


def _quality(q: D.Quality, account: str) -> str:
    """Settled decision quality per strategy, then recent losses for reflection."""
    keys = list(q.scores) if account == B.ALL else [account]
    rows = []
    for k in keys:
        s = q.scores[k]
        rows.append(
            [
                f"<strong>{c.e(L.STRATEGIES[k])}</strong>",
                f'<span class="num">{s.n}</span>',
                f'<span class="num">{_pctx(s.hit_rate)}</span>',
                f'<span class="num">{"—" if s.brier is None else f"{s.brier:.4f}"}</span>',
                f'<span class="num">{"—" if s.mean_edge is None else f"{s.mean_edge * 100:+.1f}¢ ±{s.se * 100:.1f}"}</span>',
                c.status("connected" if s.proven else "stale", s.verdict.upper()),
            ]
        )
    lost = D.losses(q.settled, None if account == B.ALL else account)
    refl = []
    for x in lost:
        r = x.rec
        lesson = q.lessons.get(r["decision_id"])
        call = f"{r['rating']} · P(up) {r['p_up']:.2f}" if r["p_up"] is not None else r["rating"]
        refl.append(
            [
                f'<span class="num">{_t(datetime.fromisoformat(r["decided_at"]).timestamp(), "%m-%d %H:%M")}</span>',
                c.e(L.STRATEGIES[r["strategy"]]),
                c.e(call),
                c.e("up" if x.outcome else "down"),
                f'<span class="meta" title="{c.e(r["reason"])}">{c.e(r["reason"])}</span>',
                c.e(lesson) if lesson else '<span class="meta">— not recorded</span>',
            ]
        )
    return (
        c.table(
            ["Strategy", "n", "Hit rate", "Brier", "Edge vs 50¢", "Verdict"],
            rows,
            numeric={1, 2, 3, 4},
            stack=True,
        )
        + f'<p class="meta">{q.logged} decisions in the append-only log · {len(q.settled)} settled against Kalshi outcomes · '
        "edge = hit rate − 50¢ per contract, pre-fee (fee ≈ 1.8¢) ± 1σ · Brier vs coin 0.2500 · "
        f"“no edge proven” until n ≥ {D.MIN_N} and edge &gt; 2σ</p>"
        + f"<h3>Reflection · last {D.REFLECT_N} losing decisions</h3>"
        + c.table(
            ["Time", "Strategy", "Call", "Settled", "Reason recorded", "Lesson"],
            refl,
            stack=True,
            empty="No settled losing decisions yet.",
        )
        + f'<p class="meta">lessons ≤ {D.LESSON_MAX} chars, display only — never fed back into live decisions (S2.1 gate)</p>'
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


def _svg(
    lg: L.Ledger, books: dict[str, L.StrategyBook], W: int, H: int, LBL: int, fs: int, cls: str
) -> str:
    pts = [(ts, eq) for b in books.values() for ts, eq in b.curve]
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
    targets = {k: y(float(b.curve[-1][1])) + fs / 3 for k, b in books.items()}
    targets["_base"] = base + fs / 3
    label_y = _spread(targets, fs + 3, fs, H + 20)
    x_lbl = x(t1) + 6
    parts.append(
        f'<text x="{x_lbl:.1f}" y="{label_y["_base"]:.1f}" font-size="{fs}" fill="var(--c-muted)">start {L.SLEEVE}</text>'
    )
    for key, b in books.items():
        stroke, dash = SERIES[key]
        path = " ".join(f"{x(ts):.1f},{y(float(eq)):.1f}" for ts, eq in [(t0, L.SLEEVE), *b.curve])
        parts.append(
            f'<polyline points="{path}" fill="none" stroke="{stroke}" stroke-width="1.75" '
            f'stroke-dasharray="{dash}" vector-effect="non-scaling-stroke"/>'
            f'<text x="{x_lbl:.1f}" y="{label_y[key]:.1f}" font-size="{fs}" fill="{stroke}">'
            f"{c.e(b.name.split()[0])} {float(b.curve[-1][1]):.0f}</text>"
        )
    label = "; ".join(f"{b.name} ends at {b.equity} USD" for b in books.values())
    return (
        f'<svg class="{cls}" viewBox="0 0 {W} {H + 24}" width="100%" role="img" '
        f'aria-label="{c.e(label)}">{"".join(parts)}</svg>'
    )


def _curve(lg: L.Ledger, account: str) -> str:
    books = {b.key: b for b in B.books(lg, account)}
    pts = [p for b in books.values() for p in b.curve]
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
        + _svg(lg, books, 900, 220, 130, 12, "chart-d")
        + _svg(lg, books, 420, 300, 110, 15, "chart-m")
    )


def render(
    lg: L.Ledger,
    *,
    start: str,
    now: float | None = None,
    account: str | None = None,
    status: str | None = None,
    workers: dict[str, dict] | None = None,
    supervisor_down: bool = False,
    studio: S.Studio | None = None,
    quality: D.Quality | None = None,
) -> str:
    """``lg`` must already be narrowed to the caller's grants (``demo.scope``)."""
    from algobots.demo import studio_page as SP  # imports this module

    now = time.time() if now is None else now
    studio = studio or S.load("/nonexistent")  # built-ins only
    quality = quality or D.quality(D.records(lg), lg, accounts=lg.books)
    account, status = B.account_key(account), B.status_key(status)
    if account not in lg.books and account != B.ALL:
        account = B.ALL  # routes 403 first; this only guards direct callers
    ctx = f"ctx: {_ctx_label(account)}"
    body = (
        _stateline(lg, now, account, supervisor_down)
        + _strip(lg, now, account)
        + '<div class="grid">'
        + c.panel(
            "Accounts",
            _accounts(lg, now, account, workers or {})
            + "<h3>Deployments by account · frozen params + artifact</h3>"
            + SP.deployments(studio, account, S.visible(tuple(lg.books))),
            financial=True,
            tag=TAG,
            cls="full",
        )
        + c.panel("Positions", _positions(lg, now, account), financial=True, tag=ctx)
        + c.panel("Risk", _risk(lg, now, account), financial=True, tag=ctx)
        + c.panel("Orders", _orders(lg, account, status), financial=True, tag=ctx, cls="full")
        + c.panel("Strategy performance", _performance(lg, account), financial=True, tag=ctx)
        + c.panel("Equity", _curve(lg, account), financial=True, tag=ctx)
        + c.panel(
            "Strategies",
            SP.strategies(studio, S.visible(tuple(lg.books)))
            + '<p class="meta"><a href="/demo/studio">studio: deploy a version with allocation preview →</a></p>',
            financial=True,
            tag="TEMPLATES: TEST ONLY",
            cls="full",
        )
        + c.panel(
            "Decision quality", _quality(quality, account), financial=True, tag=ctx, cls="full"
        )
        + "</div>"
    )
    title = "AlgoBots — paper trading terminal"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="refresh" content="60">\n'
        f"<title>{title}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f'<div class="chrome">{_header(lg, now, account)}{_banner(start)}</div>\n'
        f'<main id="main" data-screen="demo" data-account="{account}">\n<h1 class="sr-only">{title}</h1>\n{body}\n</main>\n'
        f"<script>{CLOCK}{KEYS}</script>\n</body>\n</html>\n"
    )
