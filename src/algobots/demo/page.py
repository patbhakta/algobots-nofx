# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Live paper-trading terminal: Accounts / Positions / Orders / Risk / Decision quality.

Selecting an account (``?account=``) sets the context every pane filters to;
``all`` is the aggregate. Data comes from ``demo.blotter`` so the page and
the JSON endpoints share one source.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlencode

from algobots.api.approvals.models import ActionLedger, ApprovalRequest
from algobots.api.approvals.service import aware_utc
from algobots.api.models import Account
from algobots.dashboard.design import components as c
from algobots.demo import accounts as A
from algobots.demo import blotter as B
from algobots.demo import decisions as D
from algobots.demo import ledger as L
from algobots.demo import quality as Q
from algobots.demo import studio as S
from algobots.demo import tickets as T
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
APPROVAL = {"auto": "Auto", "semi_auto": "Semi-auto"}


@dataclass
class Registry:
    """S4.1 registry rows + S4.3 approval queue, already narrowed to the caller (ALG-3266).

    ``accounts`` holds granted strategy accounts plus, for full-grant callers only,
    the ticket-only accounts (Semi-auto, LIVE). ``can_trade`` gates the ticket and
    the Action Center the same way the kill switch is gated: every grant.
    """

    accounts: list[tuple[Account, tuple[str, str]]]  # (account, (health kind, text))
    pending: list[ApprovalRequest] = field(default_factory=list)
    ledger: list[ActionLedger] = field(default_factory=list)
    ticket: dict | None = None
    can_trade: bool = False

    def by_key(self) -> dict[str, tuple[Account, tuple[str, str]]]:
        return {k: r for r in self.accounts for k in [A.strategy_key(r[0])] if k}

    def ticket_only(self) -> list[tuple[Account, tuple[str, str]]]:
        return [r for r in self.accounts if A.strategy_key(r[0]) is None]


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


def _accounts(
    lg: L.Ledger, now: float, account: str, workers: dict[str, dict], reg: Registry | None
) -> str:
    """Selectable rows (click, or ↑/↓ + Enter); ``All`` is the aggregate."""
    day = B.today(now)
    heads = ["Account", "Broker", "Mode", "Active", "Approval", "Session"]
    heads += ["Allocated", "Equity", "Net P&L", "Today", "State", "Worker"]
    numeric = {6, 7, 8, 9}
    regs = reg.by_key() if reg else {}
    dash = '<span class="meta">—</span>'

    def registry_cells(a: Account | None, health: tuple[str, str] | None) -> list[str]:
        if a is None:
            return [dash, c.env_badge("PAPER"), dash, dash, dash]
        return [
            c.e(a.broker),
            c.env_badge(A.environment(a)),
            c.status("ready", "active") if a.status == "active" else c.status("todo", a.status),
            c.e(APPROVAL.get(a.approval_mode, a.approval_mode)),
            c.status(*health),
        ]

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
        a, health = regs.get(key, (None, None))
        cells = [
            f'<a href="/demo{_query(key)}">{c.e(_ctx_label(key))}</a>',
            *(
                [dash, c.env_badge("PAPER"), dash, dash, dash]
                if key == B.ALL
                else registry_cells(a, health)
            ),
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
    for a, health in reg.ticket_only() if reg and account == B.ALL else []:
        env = A.environment(a)
        block = A.order_block_reason(a)
        ctx = {"id": str(a.id), "label": a.label, "environment": env}
        cells = [c.e(a.label), *registry_cells(a, health), dash, dash, dash, dash]
        cells += [
            c.action("Order", account=ctx, environment=env, disabled_reason=block)
            if block
            else c.status("connected", "TICKET ONLY"),
            dash,
        ]
        tds = "".join(
            f'<td{" class=n" if i in numeric else ""} data-label="{heads[i]}">{v}</td>'
            for i, v in enumerate(cells)
        )
        body += f'<tr class="registry-only" data-registry-account="{a.id}">{tds}</tr>'
    note = (
        ""
        if reg
        else '<p class="meta">Account registry unavailable — broker/approval/session not shown.</p>'
    )
    return note + (
        '<table class="data stack accounts" role="grid" aria-label="Accounts — select to set context">'
        f"<thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>"
    )


def _ticket(reg: Registry | None) -> str:
    if reg is None:
        return '<p class="empty">Order ticket unavailable — account registry not reachable.</p>'
    if not reg.can_trade:
        return '<p class="empty">Order ticket needs a grant on every account (same as the kill switch).</p>'
    boxes = []
    for a, _ in reg.accounts:
        block = A.order_block_reason(a)
        env = A.environment(a)
        mode = APPROVAL.get(a.approval_mode, a.approval_mode)
        desc = f'{c.e(a.label)} {c.env_badge(env)} <span class="meta">{c.e(mode)}</span>'
        # a blocked leg gets no input at all: nothing to tick, nothing to submit
        boxes.append(
            f'<div class="leg" data-leg-blocked="{a.id}">{c.status("BLOCKED", "")} {desc} '
            f'<span class="why">({c.e(block)})</span></div>'
            if block
            else f'<label class="leg"><input type="checkbox" name="account" value="{a.id}" checked> {desc}</label>'
        )
    form = (
        '<form method="post" action="/demo/ticket" class="ticket">'
        f"<fieldset><legend>Broadcast to accounts</legend>{''.join(boxes)}</fieldset>"
        '<div class="actions"><label class="field">Side <select name="side"><option>YES</option><option>NO</option></select></label>'
        '<label class="field">Contracts <input name="qty" type="number" min="1" max="100" value="10" inputmode="numeric"></label>'
        '<label class="field"><span class="sr-only">Your name for the audit log</span>'
        '<input name="actor" maxlength="40" placeholder="your name (audit log)" autocomplete="name"></label>'
        f'<button type="submit" class="action"><span>Send ticket</span><span class="sr-only">, </span><span class="ctx">{A.SYMBOL} · PAPER legs only</span></button></div>'
        "</form>"
    )
    last = ""
    t = reg.ticket
    if t:
        legs = [
            [
                c.e(leg["account"]),
                c.status(
                    {"filled": "FILLED", "parked": "AWAITING_APPROVAL", "blocked": "BLOCKED"}[
                        leg["status"]
                    ],
                    leg["status"],
                ),
                f'<span class="meta">{c.e(leg["reason"])}</span>',
            ]
            for leg in t["legs"]
        ]
        last = (
            f"<h3>Last ticket · {c.e(t['side'])} {t['qty']:g} {A.SYMBOL} · "
            f'<span data-broadcast-state="{c.e(t["state"])}">{c.e(t["state"])}</span></h3>'
            + c.table(["Account", "Leg", "Detail"], legs, stack=True)
        )
    note = (
        '<p class="meta">Auto legs fill on paper at the 50¢ mid · Semi-auto legs park in the '
        "Action Center · LIVE legs are refused before any order exists (live gated: G-live not passed)</p>"
    )
    return form + note + last


def _action_center(reg: Registry | None) -> str:
    if reg is None:
        return '<p class="empty">Approval queue unavailable — database not reachable.</p>'
    if not reg.can_trade:
        return '<p class="empty">Action Center needs a grant on every account (same as the kill switch).</p>'
    labels = {str(a.id): a.label for a, _ in reg.accounts}
    rows = []
    for r in reg.pending:
        verdicts = "".join(
            f'<form method="post" action="/demo/approvals/{r.id}" class="inline">'
            f'<input type="hidden" name="verdict" value="{v}">'
            f'<button type="submit" class="action" data-verdict="{v}"><span>{label}</span>'
            f'<span class="sr-only">, </span><span class="ctx">{c.e(labels.get(str(r.account_id), ""))} · PAPER</span></button></form>'
            for v, label in (("approved", "Approve"), ("rejected", "Reject"))
        )
        rows.append(
            [
                _t(aware_utc(r.parked_at).timestamp(), "%H:%M:%S"),
                c.e(labels.get(str(r.account_id), str(r.account_id))),
                c.e(r.symbol),
                f'<span class="num">{r.qty:g}</span>',
                _t(aware_utc(r.expires_at).timestamp()),
                verdicts,
            ]
        )
    queue = c.table(
        ["Parked", "Account", "Contract", "Qty", "Expires", "Decision"],
        rows,
        numeric={3},
        stack=True,
        empty="No pending approvals — Semi-auto ticket legs park here.",
    )
    audit = c.table(
        ["Time", "Action", "Reason", "Latency"],
        [
            [
                _t(aware_utc(x.created_at).timestamp(), "%H:%M:%S"),
                c.e(x.action),
                f'<span class="meta">{c.e(x.reason)}</span>',
                f'<span class="num">{"—" if x.latency_ms is None else f"{x.latency_ms / 1000:.1f}s"}</span>',
            ]
            for x in reg.ledger
        ],
        numeric={3},
        stack=True,
        empty="Audit ledger is empty.",
    )
    return f"{queue}<h3>Audit ledger · append-only</h3>{audit}"


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
                f'<span class="num" id="o-{c.e(o["id"])}" data-order="{c.e(o["id"])}">{_t(o["ts"], "%m-%d %H:%M")}</span>',
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


def _risk_ticket(lg: L.Ledger, account: str, msg: str | None) -> str:
    """Order ticket: one paper order type, four paths, every leg behind the risk gate."""
    picked = set(lg.books) if account == B.ALL else {account}
    radios = "".join(
        f'<label><input type="radio" name="path" value="{p}"{" checked" if p == "single" else ""}> {p}</label>'
        for p in T.PATHS
    )
    accts = "".join(
        f'<label><input type="checkbox" name="accounts" value="{k}"{" checked" if k in picked else ""}> {c.e(n)}</label>'
        for k, n in L.STRATEGIES.items()
        if k in lg.books  # only granted accounts are offered
    )
    sides = "".join(f'<option value="{s}">{s}</option>' for s in T.SIDES)
    kinds = "".join(f'<option value="{k}">{k}</option>' for k in T.KINDS)
    kill = (
        c.status("BLOCKED", "kill switch engaged — entry legs will be denied; exits still allowed")
        if lg.kill.get("engaged")
        else ""
    )
    return (
        f'<form method="post" action="/demo/orders" class="rticket" id="ticket">'
        f'<input type="hidden" name="ctx" value="{account}">'
        f"<fieldset><legend>Path</legend>{radios}</fieldset>"
        f"<fieldset><legend>Accounts (single/split use the first; broadcast fans to all ticked)</legend>{accts}</fieldset>"
        "<fieldset><legend>Order</legend>"
        f"<label>{B.INSTRUMENT} next 15m</label>"
        f'<label>side <select name="side">{sides}</select></label>'
        f'<label>kind <select name="kind">{kinds}</select></label>'
        '<label>notional USD <input name="notional" inputmode="decimal" value="10" size="6"></label>'
        f'<label>max clip USD <input name="max_clip" inputmode="decimal" value="{L.ENVELOPE.max_order_value}" size="6"></label>'
        '<label><input type="checkbox" name="bracket" disabled aria-describedby="bracket-why"> bracket</label>'
        f'<span class="meta" id="bracket-why">{c.e(T.BRACKET_UNSUPPORTED)}</span></fieldset>'
        "<fieldset><legend>Basket (one per line: account side notional)</legend>"
        '<textarea name="basket" rows="3" placeholder="laya YES 10&#10;jev NO 5"></textarea></fieldset>'
        f'<div class="actions">{kill}<button type="submit" class="action" data-environment="PAPER">'
        f'<span>Submit paper order</span><span class="ctx">every leg → risk gate</span></button></div>'
        f'<p class="meta">{c.e(T.PAPER_NOTE)} · gate per leg: kill switch → sleeve floor → '
        f"daily loss −{L.ENVELOPE.max_daily_loss} → rate breakers → clamp to {L.ENVELOPE.max_order_value} USD · exits privileged</p>"
        + (f'<p class="rticket-msg" role="status">{c.e(msg)}</p>' if msg else "")
        + "</form>"
    )


def _ticket_blotter(parents: list[T.Parent], account: str) -> str:
    """Parent → child legs, newest parent first, with per-leg status and reason."""
    rows = []
    for p in sorted(parents, key=lambda p: p.ts, reverse=True)[:20]:
        legs = [x for x in p.legs if account == B.ALL or x.account == account]
        if not legs:
            continue
        rows.append(
            [
                f'<span class="num">{_t(p.ts, "%m-%d %H:%M:%S")}</span>',
                f"<strong>{c.e(p.path)}</strong> {c.e(p.id)}",
                "",
                "",
                "",
                f'<span class="num">{len(legs)} legs</span>',
                "",
                c.status(
                    "ready"
                    if p.state == "sent"
                    else "BLOCKED"
                    if p.state == "rejected"
                    else "PARTIALLY_FILLED",
                    p.state,
                ),
                "",
            ]
        )
        for x in legs:
            filled = x.status == "filled"
            rows.append(
                [
                    "",
                    f'<span class="meta">└ leg {x.seq}</span>',
                    c.e(L.STRATEGIES[x.account]),
                    c.e(x.side),
                    c.e(x.kind),
                    f'<span class="num">{x.qty}</span>' if filled else NONE,
                    c.money(_usd(x.notional)) if filled else NONE,
                    c.status(
                        "FILLED" if filled else "BLOCKED",
                        x.status + (" · clamped" if x.clamped else ""),
                    ),
                    f'<span class="meta" title="{c.e(x.reason)}">{c.e(x.reason)}</span>',
                ]
            )
    return (
        c.table(
            [
                "Time",
                "Parent / leg",
                "Account",
                "Side",
                "Kind",
                "Qty",
                "Notional",
                "Status",
                "Reason",
            ],
            rows,
            numeric={5, 6},
            stack=True,
            empty="No ticket orders yet — submit one from the Order ticket.",
        )
        + '<p class="meta"><a href="/demo/api/orders">JSON</a> · legs carry parent_id</p>'
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
        + _debate(q.debate)
    )


def _debate(d: D.Debate | None) -> str:
    """Bull vs bear: the intervals where Laya and Jev called opposite directions."""
    if d is None:
        return ""

    def arg(r: dict) -> str:
        p = "" if r.get("p_up") is None else f" · P(up) {r['p_up']:.2f}"
        return (
            f"<strong>{c.e(L.STRATEGIES[r['strategy']])}</strong>{c.e(p)}"
            f'<br><span class="meta" title="{c.e(r["reason"])}">{c.e(r["reason"])}</span>'
        )

    rows = []
    for x in d.clashes[: D.REFLECT_N]:
        won = (
            '<span class="meta">open</span>'
            if x.winner is None
            else f"{'up' if x.outcome else 'down'} → <strong>{c.e(L.STRATEGIES[x.winner])}</strong>"
        )
        rows.append(
            [
                f'<span class="num">{_t(datetime.fromisoformat(x.decided_at).timestamp(), "%m-%d %H:%M")}</span>',
                arg(x.bull),
                arg(x.bear),
                won,
            ]
        )
    tally = " · ".join(f"{L.STRATEGIES[k]} {n}" for k, n in d.wins.items())
    agreed = (
        f"agreed on {d.agreed} settled intervals, hit {_pctx(d.agreed_hits / d.agreed)}"
        if d.agreed
        else "no settled agreements yet"
    )
    return (
        f"<h3>Analyst debate · bull vs bear · last {D.REFLECT_N} disagreements</h3>"
        + c.table(
            ["Time", "Bull (up)", "Bear (down)", "Settled → winner"],
            rows,
            stack=True,
            empty="Laya and Jev have not disagreed on an interval yet.",
        )
        + f'<p class="meta">{len(d.clashes)} disagreements, {d.settled} settled · debates won: {c.e(tally)} · {agreed} · '
        "arguments are each analyst’s recorded reason, not generated text · display only — "
        "no debate outcome changes an order (TradingAgents researcher-debate pattern)</p>"
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


def _f(x: float | None, fmt: str = ".4f") -> str:
    return "—" if x is None else format(x, fmt)


def _harness_pane(q: dict) -> str:
    """Decision quality (S2.2 harness) + latest reflections (S2.1), per strategy."""
    rows, cal, refl = [], [], []
    for s in q["strategies"].values():
        ci = s["hit_rate_wilson_95"]
        rc = s["random_control"]
        kind = "APPROVED" if s["edge_demonstrated"] else "not_granted"
        rows.append(
            [
                f"<strong>{c.e(s['name'])}</strong>",
                f'<span class="num" data-q="brier">{_f(s["brier"])}</span>'
                f' <span class="meta">coin {_f(s["coin_brier"])}</span>',
                f'<span class="num" data-q="hit">{_pctx(s["hit_rate"])}</span>'
                + (f' <span class="meta">[{ci[0]:.1%}, {ci[1]:.1%}]</span>' if ci else ""),
                f'<span class="num" style="white-space:nowrap"><span data-q="settled">{s["settled"]}</span>'
                f' / <span data-q="pending">{s["pending"]}</span></span>',
                c.status(kind, s["verdict"].lower())
                + f'<br><span class="meta">n={s["sample_size"]} · {rc["seeds"]} random seeds, '
                f'{rc["certified"]} certified</span>',
            ]
        )
        cal.append(
            [c.e(s["name"])]
            + [
                f'<span class="num">{_pctx(b["hit_rate"])}</span> <span class="meta">n={b["count"]}</span>'
                for b in s["calibration"]
            ]
        )
        for r in s["reflections"]:
            hit = c.status("FILLED" if r["hit"] else "REJECTED", "hit" if r["hit"] else "miss")
            refl.append(
                f'<li data-decision="{c.e(r["decision_id"])}"><a href="#o-{c.e(r["decision_id"])}">'
                f"{c.e(s['name'])} · {c.e(r['event'].split('-')[-1])}</a> {hit} "
                f'<span class="meta">{c.e(r["text"])}</span></li>'
            )
    if not rows:
        return '<p class="empty">No accounts in this context.</p>'
    buckets = [b["bucket"] for b in next(iter(q["strategies"].values()))["calibration"]]
    return (
        '<p class="halt-note"><strong>No validated edge</strong> unless the harness verdict says '
        "otherwise — paper results, not a performance claim.</p>"
        f'<p class="meta">Break-even hit {q["break_even"]:.2%} at 50c + 7% taker fee · '
        "Brier = harness 3-band score, lower is better, coin 0.5000 · "
        "verdict = harness Wilson-95 lower bound vs majority-label baseline</p>"
        + c.table(
            ["Strategy", "Brier vs coin", "Hit rate [Wilson 95%]", "Settled / pending", "Harness verdict"],
            rows,
            numeric={1, 2, 3},
            stack=True,
        )
        + "<h3>Calibration · hit rate by P(called side)</h3>"
        + c.table(["Strategy", *buckets], cal, numeric=set(range(1, len(buckets) + 1)), stack=True)
        + "<h3>Latest reflections · written at settlement</h3>"
        + (
            f'<ul class="reflections">{"".join(refl)}</ul>'
            if refl
            else '<p class="empty">No settled decisions yet — reflections are written only at settlement.</p>'
        )
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
    registry: Registry | None = None,
    harness: dict | None = None,
    tickets: list[T.Parent] | None = None,
    ticket_msg: str | None = None,
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
    harness = Q.quality(lg, account=account) if harness is None else harness
    body = (
        _stateline(lg, now, account, supervisor_down)
        + _strip(lg, now, account)
        + '<div class="grid">'
        + c.panel(
            "Accounts",
            _accounts(lg, now, account, workers or {}, registry)
            + "<h3>Deployments by account · frozen params + artifact</h3>"
            + SP.deployments(studio, account, S.visible(tuple(lg.books))),
            financial=True,
            tag=TAG,
            cls="full",
        )
        + (
            c.panel("Order ticket · broadcast", _ticket(registry), cls="ticket-panel")
            + c.panel("Action Center · pending approvals", _action_center(registry))
            if account == B.ALL
            else ""
        )
        + c.panel("Positions", _positions(lg, now, account), financial=True, tag=ctx)
        + c.panel("Risk", _risk(lg, now, account), financial=True, tag=ctx)
        + c.panel(
            "Order ticket · single / broadcast / basket / split",
            _risk_ticket(lg, account, ticket_msg),
            financial=True,
            tag=TAG,
        )
        + c.panel(
            "Ticket blotter", _ticket_blotter(tickets or [], account), financial=True, tag=ctx
        )
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
        + c.panel(
            "Harness verdict · calibration · reflections",
            _harness_pane(harness),
            financial=True,
            tag=ctx,
            cls="full",
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
