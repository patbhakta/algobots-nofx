# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Live paper-trading dashboard, NoFX pattern (ALG-3288).

One overview screen (headline, equity chart, a card per strategy, positions,
latest activity); every dense pane is a tab (``?view=``). Selecting an account
(``?account=``) sets the context every view filters to; ``all`` is the
aggregate. Data comes from ``demo.blotter`` so the page and the JSON
endpoints share one source.
"""

from __future__ import annotations

import json
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
from algobots.demo import bars as BARS
from algobots.demo import blotter as B
from algobots.demo import decisions as D
from algobots.demo import gate as G
from algobots.demo import ledger as L
from algobots.demo import quality as Q
from algobots.demo import studio as S
from algobots.demo import tickets as T
from algobots.demo.theme import CLOCK, CSS, HOVER, KEYS
from algobots.engine.workers import template as TPL

INTERVAL_S = 15 * 60
STALE_AFTER_S = 25 * 60  # one missed observer run plus slack
SERIES = {  # strategy -> (stroke var, dash) — dash + direct label, never colour alone
    "laya": ("var(--s-laya)", ""),  # categorical blue/orange/violet: validated on --c-panel
    "jev": ("var(--s-jev)", "6 4"),
    "coin": ("var(--s-coin)", "2 3"),
}
VIEWS = {  # ?view= -> tab label; overview is the default and the only non-tab screen
    "overview": "Overview",
    "orders": "Orders",
    "risk": "Risk & kill switch",
    "quality": "Decision quality",
    "strategies": "Strategies",
    "accounts": "Accounts",
    "trade": "Trade",
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


def view_key(raw: str | None) -> str:
    return raw if raw in VIEWS else "overview"


def _query(account: str, status: str | None = None, view: str | None = None) -> str:
    pairs = (("account", account), ("view", view), ("status", status))
    q = {k: v for k, v in pairs if v and v not in (B.ALL, "overview")}
    return c.e(f"?{urlencode(q)}") if q else ""  # HTML-escaped: only ever lands in attributes


def _ctx_label(account: str) -> str:
    return "All accounts" if account == B.ALL else _name(account)


def _name(account: str) -> str:
    return L.STRATEGIES.get(account) or S.ACCOUNTS[account].label


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


def _executor(lg: L.Ledger) -> str:
    """Who filled the headline sleeves, and what is still assumed (ALG-3289)."""
    if lg.executor == L.REFERENCE:
        what = "fills computed by the reference model (Nautilus not installed here)"
    else:
        what = "fills, fees, settlement and sleeve cash read back from the engine"
    return (
        f'<span data-executor="{c.e(lg.executor)}">executor <strong>{c.e(lg.executor)}</strong> · '
        f"{what} · quotes at the assumed 50¢ mid (feed has no order book) · no broker orders</span>"
    )


def _banner(lg: L.Ledger, start: str) -> str:
    return (
        '<div class="disclosure" role="note"><strong>PAPER TRADING</strong>'
        f"<span>since {c.e(start)} · $5–15/trade · whole contracts + Kalshi taker fee</span>"
        f"{_executor(lg)}"
        '<span class="wide">decides from prior settled intervals only · refresh 60s · ↑/↓ + Enter selects account</span></div>'
    )


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
    lg: L.Ledger,
    now: float,
    account: str,
    workers: dict[str, dict],
    reg: Registry | None,
    eq_rows: str = "",
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
            f'<a href="/demo{_query(key, view="accounts")}">{c.e(_ctx_label(key))}</a>',
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
        return f'<tr class="arow{" sel" if sel else ""}" data-row="{key}">{tds}</tr>'

    th = "".join(
        f'<th scope="col"{" class=n" if i in numeric else ""}>{h}</th>' for i, h in enumerate(heads)
    )
    body = row(B.ALL, list(lg.books.values())) + "".join(row(k, [b]) for k, b in lg.books.items())
    body += eq_rows
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
        '<table class="data stack accounts">'
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


def _eq_rows(tpl: dict[str, dict], account: str, tw: dict[str, dict]) -> str:
    """Accounts-pane rows for the equities paper accounts run by template workers."""
    heads = ["Account", "Broker", "Mode", "Active", "Approval", "Session"]
    heads += ["Allocated", "Equity", "Net P&L", "Today", "State", "Worker"]
    out = []
    for key in B.EQUITY:
        a = tpl.get(key)
        deps = a["deployments"] if a else []
        ready = sum(1 for d in deps if (tw.get(d.id) or {}).get("state") == "ready")
        running = sum(1 for d in deps if d.state == "running")
        state = (
            c.status("connected", f"{running} RUNNING")
            + (
                f' <span class="meta">{len(deps) - running} pending</span>'
                if running < len(deps)
                else ""
            )
            if deps
            else c.status("disconnected", "NO DEPLOYMENT")
        )
        cells = [
            f'<a href="/demo{_query(key)}">{c.e(_name(key))}</a>',
            '<span class="meta">studio paper</span>',
            c.env_badge("PAPER"),
            NONE,
            c.e(APPROVAL["auto"]),
            NONE,
            c.money(_usd(a["allocated"])) if a else NONE,
            c.money(_usd(a["equity"])) if a else NONE,
            c.money(_usd(a["pnl"]), signed=True) if a else NONE,
            NONE,
            state,
            f'<span class="meta">{ready}/{len(deps)} template workers ready · {a["orders"] if a else 0} orders</span>',
        ]
        sel = key == account
        tds = "".join(
            f'<td{" class=n" if i in (6, 7, 8, 9) else ""} data-label="{heads[i]}">{v}</td>'
            for i, v in enumerate(cells)
        )
        out.append(
            f'<tr class="acct{" sel" if sel else ""}" data-account="{key}" '
            f'data-href="/demo{_query(key)}" tabindex="0" aria-selected="{str(sel).lower()}">{tds}</tr>'
        )
    return "".join(out)


def _tpl_positions(rows: list[dict]) -> str:
    body = [
        [
            c.e(_name(p["account"])),
            f'<span class="meta">{c.e(p["deployment"])}@{c.e(p["artifact"])}</span>',
            c.e(p["instrument"]),
            c.e(p["side"]),
            f'<span class="num">{p["qty"]}</span>',
            f'<span class="num">{p["avg_price"]}</span>',
            f'<span class="num">{p["mark"]}</span>',
            c.money(_usd(p["unrealized_pnl"]), signed=True),
        ]
        for p in rows
    ]
    return f"<h3>Template positions · {BARS.SOURCE}</h3>" + c.table(
        ["Account", "Deployment", "Symbol", "Side", "Qty", "Avg px", "Mark", "Unreal. P&L"],
        body,
        numeric={4, 5, 6, 7},
        stack=True,
        empty="No open template positions: flat.",
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


def _orders(lg: L.Ledger, account: str, status: str | None, templates: list[dict]) -> str:
    counts = {s: len(B.orders(lg, account, s, None, templates=templates)) for s in B.STATUSES}
    links = "".join(
        f'<a href="/demo{_query(account, s, "orders")}" class="filt{" on" if s == status else ""}"'
        f"{' aria-current=true' if s == status else ''}>"
        f"{s or 'all'} {sum(counts.values()) if s is None else counts[s]}</a>"
        for s in (None, *B.STATUSES)
    )
    json_link = f"/demo/api/orders{_query(account, status)}"
    kind = {"filled": "FILLED", "blocked": "BLOCKED", "abstain": "ABSTAIN"}
    rows = []
    for o in B.orders(lg, account, status, ORDER_ROWS, templates=templates):
        filled = o["status"] == "filled"
        rows.append(
            [
                f'<span class="num" id="o-{c.e(o["id"])}" data-order="{c.e(o["id"])}">{_t(o["ts"], "%m-%d %H:%M")}</span>',
                f'<span title="{c.e(o["deployment"])} · artifact {c.e(o["artifact"])}">{c.e(_name(o["account"]))}</span>'
                f'<span class="meta dep" data-deployment="{c.e(o["deployment"])}"> {c.e(o["deployment"])}@{c.e(o["artifact"])}</span>',
                c.e(o["instrument"].split("-")[-1]),
                c.e(o["side"] or "—"),
                f'<span class="num" title="client order {c.e(o.get("order_id") or "—")}" data-order-id="{c.e(o.get("order_id") or "")}">{o["qty"]}</span>'
                if filled
                else NONE,
                f'<span class="num">{o["price"]}</span>' if filled else NONE,
                c.money(_usd(o["notional"])) if filled else NONE,
                c.money(_usd(o["fee"])) if filled else NONE,
                c.money(_usd(o["pnl"]), signed=True) if filled and o["pnl"] is not None else NONE,
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
    """Order ticket: one paper order type, five paths, every leg behind the risk gate."""
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
        f"<fieldset><legend>Accounts (single/split use the first; broadcast and bracket fan to all ticked)</legend>{accts}"
        '<label>mode <select name="mode" aria-describedby="live-why">'
        '<option value="PAPER" selected>PAPER</option>'
        f'<option value="LIVE" disabled>LIVE — {c.e(G.LIVE_DISABLED)}</option></select></label>'
        f'<span class="meta" id="live-why">LIVE hard-disabled: {c.e(G.LIVE_DISABLED)}</span></fieldset>'
        "<fieldset><legend>Order</legend>"
        f"<label>{B.INSTRUMENT} next 15m</label>"
        f'<label>side <select name="side">{sides}</select></label>'
        f'<label>kind <select name="kind">{kinds}</select></label>'
        '<label>notional USD <input name="notional" inputmode="decimal" value="10" size="6"></label>'
        f'<label>max clip USD <input name="max_clip" inputmode="decimal" value="{L.ENVELOPE.max_order_value}" size="6"></label>'
        '<label>bracket take-profit <input name="take_profit" inputmode="decimal" value="0.70" size="4"></label>'
        '<label>stop <input name="stop" inputmode="decimal" value="0.30" size="4"></label>'
        f'<span class="meta" id="bracket-why">{c.e(T.BRACKET_NOTE)}</span></fieldset>'
        "<fieldset><legend>Basket (one per line: account side notional)</legend>"
        '<textarea name="basket" rows="3" placeholder="laya YES 10&#10;jev NO 5"></textarea></fieldset>'
        f'<div class="actions">{kill}<button type="submit" class="action" data-environment="PAPER">'
        f'<span>Submit paper order</span><span class="ctx">every leg → risk gate</span></button></div>'
        f'<p class="meta">{c.e(T.PAPER_NOTE)} · gate per leg (same as the strategies): mode → kill switch → sleeve floor → '
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
        cancel = (
            f'<form method="post" action="/demo/orders/{c.e(p.id)}/cancel" class="inline">'
            f'<button type="submit" class="action">Cancel {c.e(p.id)}</button></form>'
            if any(x.status in ("working", "submitted") for x in legs)
            else ""
        )
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
                    p.state + (" · cancelled" if p.cancelled_ts else ""),
                ),
                cancel,
            ]
        )
        for x in legs:
            rows.append(
                [
                    "",
                    f'<span class="meta">└ leg {x.seq}{"" if x.role == "order" else " " + c.e(x.role)}</span>',
                    c.e(L.STRATEGIES[x.account]),
                    c.e(x.side),
                    c.e(x.kind),
                    f'<span class="num">{x.qty}</span>' if x.qty else NONE,
                    c.money(_usd(x.notional)) if x.qty else NONE,
                    c.status(
                        {
                            "filled": "FILLED",
                            "submitted": "pending",
                            "working": "pending",
                            "cancelled": "todo",
                        }.get(x.status, "BLOCKED"),
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
        f'<line x1="{PAD}" x2="{W - LBL}" y1="{base:.1f}" y2="{base:.1f}" stroke="var(--c-rule-strong)" stroke-width="1"/>'
    ]
    for ts in lg.refill_ts:
        if t0 <= ts <= t1:
            parts.append(
                f'<line x1="{x(ts):.1f}" x2="{x(ts):.1f}" y1="{PAD}" y2="{H - PAD}" stroke="var(--c-attention)" stroke-dasharray="3 3"/>'
                f'<text x="{x(ts) + (-3 if x(ts) > (W - LBL) / 2 else 3):.1f}" y="{PAD + fs}" font-size="{fs - 1}" '
                f'text-anchor="{"end" if x(ts) > (W - LBL) / 2 else "start"}" fill="var(--c-muted)">refill {_t(ts)}</text>'
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
            f'<polyline points="{path}" fill="none" stroke="{stroke}" stroke-width="2" '
            f'stroke-dasharray="{dash}" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>'
            # labels wear text ink; the coloured swatch in the legend carries identity
            f'<text x="{x_lbl:.1f}" y="{label_y[key]:.1f}" font-size="{fs}" fill="var(--c-ink)">'
            f"{c.e(b.name.split()[0])} {float(b.curve[-1][1]):.0f}</text>"
        )
    parts.append(
        f'<line class="xhair" x1="0" x2="0" y1="{PAD}" y2="{H - PAD}" stroke="var(--c-muted)" visibility="hidden"/>'
    )
    # hover data: one entry per interval (downsampled), every series at that interval
    by_ts = {k: dict(b.curve) for k, b in books.items()}
    stamps = sorted({ts for b in books.values() for ts, _ in b.curve})
    step = max(1, len(stamps) // 240)
    hover = [
        [
            round(x(ts), 1),
            _t(ts, "%b %d %H:%M"),
            *[[b.name, f"{by_ts[k][ts]:.2f}"] for k, b in books.items() if ts in by_ts[k]],
        ]
        for ts in [*stamps[::step], *([stamps[-1]] if (len(stamps) - 1) % step else [])]
    ]
    label = "; ".join(f"{b.name} ends at {b.equity} USD" for b in books.values())
    return (
        f'<svg class="{cls}" viewBox="0 0 {W} {H + 24}" width="100%" role="img" '
        f"aria-label=\"{c.e(label)}\" data-pts='{c.e(json.dumps(hover, ensure_ascii=False))}'>{''.join(parts)}</svg>"
    )


def _legend(books: list[L.StrategyBook]) -> str:
    if len(books) < 2:  # one series: the panel title names it
        return ""
    items = "".join(
        f'<span><i style="border-top-color:{SERIES[b.key][0]};border-top-style:{"dashed" if SERIES[b.key][1] else "solid"}"></i>{c.e(b.name)}</span>'
        for b in books
    )
    return f'<div class="legend" aria-hidden="true">{items}</div>'


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
        f'<p class="meta">Sleeve equity, USD · {_t(t0, "%b %d %H:%M")} → {_t(t1, "%b %d %H:%M")} · one point per 15m interval · '
        f'hover for values · <a href="/demo{_query(account, view="orders")}">every order as a table →</a>{refills}</p>'
        + _legend(list(books.values()))
        + '<div class="chartbox">'
        + _svg(lg, books, 900, 260, 130, 12, "chart-d")
        + _svg(lg, books, 420, 300, 110, 15, "chart-m")
        + '<div class="tip" role="presentation"></div></div>'
    )


def _f(x: float | None, fmt: str = ".4f") -> str:
    return "—" if x is None else format(x, fmt)


def _harness_pane(q: dict, orders: str = "") -> str:
    """Decision quality (S2.2 harness) + latest reflections (S2.1), per strategy.

    ``orders`` is the Orders-tab URL the reflection links jump into (ALG-3288).
    """
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
                f"{rc['certified']} certified</span>",
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
                f'<li data-decision="{c.e(r["decision_id"])}"><a href="{orders}#o-{c.e(r["decision_id"])}">'
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
            [
                "Strategy",
                "Brier vs coin",
                "Hit rate [Wilson 95%]",
                "Settled / pending",
                "Harness verdict",
            ],
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


def _spark(b: L.StrategyBook) -> str:
    """Card sparkline: one series, start-capital rule, no axes; the card text carries values."""
    pts = [(b.curve[0][0], L.SLEEVE), *b.curve] if b.curve else []
    if len(pts) < 2:
        return '<p class="meta">No decisions yet.</p>'
    W, H, PAD = 240, 48, 3
    t0, t1 = pts[0][0], pts[-1][0]
    vs = [float(v) for _, v in pts] + [float(L.SLEEVE)]
    lo, hi = min(vs), max(vs)
    span_t, span_v = (t1 - t0) or 1, (hi - lo) or 1

    def xy(ts: float, v: float) -> str:
        return f"{(ts - t0) / span_t * W:.1f},{PAD + (hi - v) / span_v * (H - 2 * PAD):.1f}"

    base = PAD + (hi - float(L.SLEEVE)) / span_v * (H - 2 * PAD)
    line = " ".join(xy(ts, float(v)) for ts, v in pts)
    stroke, dash = SERIES[b.key]
    return (
        f'<svg class="spark" viewBox="0 0 {W} {H}" preserveAspectRatio="none" role="img" '
        f'aria-label="{c.e(b.name)} equity from {L.SLEEVE} to {b.equity} USD">'
        f"<title>{c.e(b.name)}: {L.SLEEVE} → {b.equity.quantize(L.CENT)} USD over {len(b.curve)} intervals</title>"
        f'<line x1="0" x2="{W}" y1="{base:.1f}" y2="{base:.1f}" stroke="var(--c-rule-strong)" stroke-dasharray="2 3" vector-effect="non-scaling-stroke"/>'
        f'<polyline points="{line}" fill="none" stroke="{stroke}" stroke-width="2" stroke-dasharray="{dash}" '
        'stroke-linejoin="round" vector-effect="non-scaling-stroke"/></svg>'
    )


def _signed_usd(x: Decimal) -> str:
    return f"{'+' if x > 0 else '−' if x < 0 else ''}${abs(x).quantize(L.CENT):,}"


def _switcher(lg: L.Ledger, account: str, view: str) -> str:
    """Account context: pills (click, or ←/→ + Enter); ``All strategies`` is the aggregate."""
    pills = "".join(
        f'<a class="acct{" sel" if k == account else ""}" data-account="{k}" '
        f'href="/demo{_query(k, view=view)}" data-href="/demo{_query(k, view=view)}"'
        f"{' aria-current=true' if k == account else ''}>"
        f"{c.e('All strategies' if k == B.ALL else _name(k) if k in B.EQUITY else L.STRATEGIES[k])}</a>"
        for k in (B.ALL, *lg.books, *B.EQUITY)
    )
    return f'<nav class="switcher" aria-label="Strategy context">{pills}</nav>'


def _tabs(account: str, view: str, reg: Registry | None) -> str:
    pending = len(reg.pending) if reg and reg.can_trade else 0
    out = []
    for k, label in VIEWS.items():
        count = (
            f'<span class="count" title="pending approvals">{pending}</span>'
            if k == "trade" and pending
            else ""
        )
        on = k == view
        out.append(
            f'<a href="/demo{_query(account, view=k)}" class="{"on" if on else ""}"'
            f'{" aria-current=page" if on else ""} data-view="{k}">{c.e(label)}{count}</a>'
        )
    return f'<nav class="tabs" aria-label="Dashboard views">{"".join(out)}</nav>'


def _attention(
    lg: L.Ledger,
    now: float,
    account: str,
    workers: dict[str, dict],
    reg: Registry | None,
    supervisor_down: bool,
) -> list[str]:
    """Plain-English list of what needs a human, most severe first; [] = nothing."""
    out, day = [], B.today(now)
    q = lambda v: f"/demo{_query(account, view=v)}"  # noqa: E731
    if lg.kill.get("engaged"):
        out.append(
            c.status("BLOCKED", "Kill switch engaged")
            + f' <span>all new entries are blocked. <a href="{q("risk")}">Review →</a></span>'
        )
    for b in B.books(lg, account):
        h = B.halt(lg, b, day)
        if h:
            out.append(
                c.status("BLOCKED", "Halted")
                + f' <span>{c.e(b.name)} stopped trading: {c.e(h)}. <a href="{q("risk")}">Why →</a></span>'
            )
    if lg.last_ts is None or now - lg.last_ts >= STALE_AFTER_S:
        out.append(
            c.status("disconnected", "No fresh data")
            + " <span>the market feed is not updating.</span>"
        )
    elif supervisor_down:
        out.append(
            c.status("disconnected", "Workers down")
            + " <span>the strategy worker supervisor is not running.</span>"
        )
    for k in B.books(lg, account):
        w = workers.get(k.key) or {}
        if w.get("state") == "exited":
            out.append(
                c.status("BLOCKED", "Worker stopped")
                + f' <span>{c.e(k.name)} worker exited (code {c.e(w.get("exit_code"))}). <a href="{q("accounts")}">Details →</a></span>'
            )
    if account == B.ALL and reg and reg.can_trade and reg.pending:
        n = len(reg.pending)
        out.append(
            c.status("AWAITING_APPROVAL", "Approval needed")
            + f' <span>{n} order{"s" * (n > 1)} waiting for you. <a href="{q("trade")}">Approve or reject →</a></span>'
        )
    return out


def _hero(
    lg: L.Ledger,
    now: float,
    account: str,
    start: str,
    quality: D.Quality,
    workers: dict[str, dict],
    reg: Registry | None,
    supervisor_down: bool,
) -> str:
    books = B.books(lg, account)
    equity = sum((b.equity for b in books), Decimal(0))
    allocated = sum((b.allocated for b in books), Decimal(0))
    pnl = equity - allocated
    opening = L.SLEEVE * len(books)
    ret = f"{pnl / opening * 100:.2f}"
    day = B.today(now)
    today = sum((B.day_pnl(b, day) for b in books), Decimal(0))
    fills_today = sum(1 for b in books for d in b.fills if L._day(d.ts) == day)
    fees = sum((b.fees for b in books), Decimal(0))
    open_pos = len(B.positions(lg, now, account))
    direction = "up" if pnl > 0 else "down" if pnl < 0 else "flat at"
    amount = f"${abs(pnl).quantize(L.CENT):,}" if pnl else f"${allocated.quantize(L.CENT):,}"
    if account == B.ALL:
        who = (
            f"<strong>{len(books)} strategies</strong> are paper-trading Kalshi's 15-minute "
            f"Bitcoin up/down contracts, each with a ${L.SLEEVE} simulated budget."
        )
    else:
        s = quality.scores.get(account)
        verdict = f" Verdict so far: <strong>{c.e(s.verdict)}</strong>." if s else ""
        who = (
            f"<strong>{c.e(L.STRATEGIES[account])}</strong> is paper-trading Kalshi's 15-minute "
            f"Bitcoin up/down contracts with a ${L.SLEEVE} simulated budget.{verdict}"
        )
    lede = (
        f"<p>{who} Since {c.e(start)} {'they are' if account == B.ALL else 'it is'} "
        f'<strong class="{"pos" if pnl > 0 else "neg" if pnl < 0 else ""}">{direction} {amount}</strong>'
        f" ({'+' if pnl > 0 else ''}{ret}%) after fees. No real money is at risk.</p>"
    )
    items = _attention(lg, now, account, workers, reg, supervisor_down)
    needs = (
        "<h2>Needs your attention</h2><ul>" + "".join(f"<li>{i}</li>" for i in items) + "</ul>"
        if items
        else '<h2>Needs your attention</h2><p class="meta">Nothing — everything is running normally.</p>'
    )
    tiles = [
        (
            "Equity",
            c.money(_usd(equity)),
            f"started at {opening} USD"
            + (f" + {allocated - opening} refilled" if allocated > opening else ""),
        ),
        (
            "Net P&L",
            c.money(_usd(pnl), signed=True),
            f"{'+' if pnl > 0 else ''}{ret}% on starting capital"
            + (" · refills excluded" if lg.refill_ts else "")
            + f" · {_signed_usd(-fees)} fees",
        ),
        ("Today", c.money(_usd(today), signed=True), f"{fills_today} trades · {day} UTC"),
        (
            "Open positions",
            f'<span class="num">{open_pos}</span>',
            "each contract settles within 15 minutes"
            if open_pos
            else "flat — every contract has settled",
        ),
    ]
    tile_html = "".join(
        f'<div class="tile"><div class="label">{c.e(lbl)}</div><div class="value">{val}</div>'
        f'<div class="meta">{c.e(meta)}</div></div>'
        for lbl, val, meta in tiles
    )
    return (
        f'<section class="hero" aria-label="Summary" data-financial="true">'
        f'<div class="lede"><h2>{c.e(_ctx_label(account))} · paper trading</h2>{lede}{needs}</div>'
        f'<div class="tiles">{tile_html}</div></section>'
    )


def _cards(
    lg: L.Ledger, now: float, account: str, quality: D.Quality, workers: dict[str, dict]
) -> str:
    day = B.today(now)
    out = []
    for k, b in lg.books.items():
        h = B.halt(lg, b, day)
        state = c.status("BLOCKED", "HALTED") if h else c.status("connected", "RUNNING")
        w = (workers.get(k) or {}).get("state")
        s = quality.scores.get(k)
        hit = _pctx(L.hit_rate(b))
        ret = b.pnl / L.SLEEVE * 100
        facts = [
            f"<span><strong>{len(b.fills)}</strong> trades</span>",
            f"<span>won <strong>{hit}</strong></span>",
            f"<span>max drop <strong>{_signed_usd(b.max_drawdown)}</strong></span>",
        ]
        if w and w != "ready":
            facts.append(f"<span>worker <strong>{c.e(w.replace('_', ' '))}</strong></span>")
        verdict = f'<span class="meta">{c.e(s.verdict)}</span>' if s else ""
        out.append(
            f'<a class="card{" sel" if k == account else ""}" href="/demo{_query(k)}" data-card="{k}" '
            f'style="--series:{SERIES[k][0]}">'
            f'<div class="top"><span class="name">{c.e(b.name)}</span>{state}</div>'
            f'<div class="top"><span class="eq">{c.money(_usd(b.equity))}</span>'
            f'<span>{c.money(_usd(b.pnl), signed=True)} <span class="meta">({ret:+.1f}%)</span></span></div>'
            f"{_spark(b)}"
            f'<div class="facts">{"".join(facts)}</div>'
            + (f'<div class="facts">{c.e(h).capitalize()}</div>' if h else "")
            + f"{verdict}"
            f'<span class="open">{"Showing this strategy" if k == account else "Open strategy →"}</span></a>'
        )
    return f'<section class="cards" aria-label="Strategies">{"".join(out)}</section>'


def _positions_brief(lg: L.Ledger, now: float, account: str) -> str:
    ps = B.positions(lg, now, account)
    if not ps:
        return '<p class="empty">Flat — no open positions. Every contract has settled (15-minute expiry).</p>'
    items = "".join(
        f'<li><span class="num meta">{p["expires_in_s"] // 60}m left</span>'
        f'<span class="what">{c.e(L.STRATEGIES[p["account"]])} holds {p["qty"]} × {c.e(p["side"])} at {p["avg_price"]}</span>'
        f"{c.money(_usd(p['unrealized_pnl']), signed=True)}</li>"
        for p in ps
    )
    return f'<ul class="feed">{items}</ul>'


def _activity(lg: L.Ledger, account: str, n: int = 8) -> str:
    """Latest decisions in words; the Orders tab has the full table."""
    items = []
    for o in B.orders(lg, account, None, limit=n):
        who = c.e(L.STRATEGIES[o["account"]])
        if o["status"] == "filled":
            what = f"{who} bought {c.e(o['side'])} for ${Decimal(o['notional']).quantize(L.CENT)}"
            amt = c.money(_usd(o["pnl"]), signed=True)
        elif o["status"] == "blocked":
            what = f"{who} was blocked by a risk limit — {c.e(o['reason'])}"
            amt = c.status("BLOCKED", "blocked")
        else:
            what = f"{who} sat out — {c.e(o['reason'])}"
        oid = o.get("order_id")
        oid_attr = f' data-order-id="{c.e(oid)}"' if oid else ""
        items.append(
            f'<li><span class="num meta" data-order="{c.e(o["id"])}"{oid_attr}>{_t(o["ts"], "%H:%M")}</span>'
            f'<span class="what" title="{c.e(o["reason"])}">{what}</span>{amt}</li>'
        )
    if not items:
        return '<p class="empty">No decisions yet.</p>'
    return (
        f'<ul class="feed">{"".join(items)}</ul>'
        f'<p class="more"><a href="/demo{_query(account, view="orders")}">All orders →</a></p>'
    )


def _overview(
    lg: L.Ledger,
    now: float,
    account: str,
    start: str,
    quality: D.Quality,
    workers: dict[str, dict],
    reg: Registry | None,
    supervisor_down: bool,
) -> str:
    ctx = f"ctx: {_ctx_label(account)}"
    return (
        _hero(lg, now, account, start, quality, workers, reg, supervisor_down)
        + c.panel("Equity", _curve(lg, account), financial=True, tag=TAG)
        + _cards(lg, now, account, quality, workers)
        + '<div class="pair">'
        + c.panel("Open positions", _positions_brief(lg, now, account), financial=True, tag=ctx)
        + c.panel("Latest activity", _activity(lg, account), financial=True, tag=ctx)
        + "</div>"
    )


def _tab(
    view: str,
    lg: L.Ledger,
    now: float,
    account: str,
    status: str | None,
    studio: S.Studio,
    quality: D.Quality,
    workers: dict[str, dict],
    reg: Registry | None,
    harness: dict,
    tickets: list[T.Parent],
    ticket_msg: str | None,
    templates: list[dict] | None = None,
    template_workers: dict[str, dict] | None = None,
) -> str:
    from algobots.demo import studio_page as SP  # imports this module
    from algobots.engine.workers import template as TPL

    ctx = f"ctx: {_ctx_label(account)}"
    templates = templates or []
    tw = template_workers or {}
    vis = S.visible(tuple(lg.books))
    tpl = TPL.summary(studio, templates, now)
    tpos = TPL.positions(studio, templates, now, account)
    if view == "orders":
        return c.panel(
            "Positions",
            _positions(lg, now, account) + (_tpl_positions(tpos) if tpos else ""),
            financial=True,
            tag=ctx,
        ) + c.panel("Orders", _orders(lg, account, status, templates), financial=True, tag=ctx)
    if view == "risk":
        return c.panel("Risk", _risk(lg, now, account), financial=True, tag=ctx)
    if view == "quality":
        return (
            c.panel("Strategy performance", _performance(lg, account), financial=True, tag=ctx)
            + c.panel("Decision quality", _quality(quality, account), financial=True, tag=ctx)
            + c.panel(
                "Harness verdict · calibration · reflections",
                _harness_pane(harness, f"/demo{_query(account, view='orders')}"),
                financial=True,
                tag=ctx,
            )
        )
    if view == "strategies":
        return c.panel(
            "Strategies",
            SP.strategies(studio, vis)
            + '<p class="meta"><a href="/demo/studio">studio: deploy a version with allocation preview →</a></p>',
            financial=True,
            tag="TEMPLATES: TEST ONLY",
        )
    if view == "accounts":
        return c.panel(
            "Accounts",
            _accounts(lg, now, account, workers, reg, _eq_rows(tpl, account, tw))
            + "<h3>Deployments by account · frozen params + artifact</h3>"
            + SP.deployments(studio, account, vis, orders=templates, workers=tw),
            financial=True,
            tag=TAG,
        )
    trade = c.panel(
        "Order ticket · single / broadcast / basket / split / bracket",
        _risk_ticket(lg, account, ticket_msg),
        financial=True,
        tag=TAG,
    ) + c.panel("Ticket blotter", _ticket_blotter(tickets, account), financial=True, tag=ctx)
    if account != B.ALL:  # registry broadcast + approvals span every account
        return trade + (
            '<p class="empty">Registry broadcast and the approval queue span every account — '
            f'<a href="/demo{_query(B.ALL, view="trade")}">switch to All strategies</a>.</p>'
        )
    return (
        trade
        + c.panel("Order ticket · broadcast", _ticket(reg), cls="ticket-panel")
        + c.panel("Action Center · pending approvals", _action_center(reg))
    )


def _eq_stateline(a: dict | None, account: str, tw: dict[str, dict]) -> str:
    """Equities template account: empty until deployed; otherwise worker readiness."""
    if not a:
        state, kind = "empty", "stale"
        text = f"EMPTY · no template deployment on {_name(account)} · deploy one from /demo/studio"
    else:
        deps = a["deployments"]
        ready = sum(1 for d in deps if (tw.get(d.id) or {}).get("state") == "ready")
        state, kind = ("connected", "connected") if ready else ("empty", "stale")
        text = (
            f"{'CONNECTED' if ready else 'STARTING'} · {_name(account)} · "
            f"{ready}/{len(deps)} template workers ready · {BARS.SOURCE}"
        )
    return f'<p class="stateline" id="state" data-state="{state}">{c.status(kind, text)}</p>'


def _eq_strip(a: dict | None) -> str:
    if not a:
        return ""
    cells = [
        c.metric("Equity", c.money(_usd(a["equity"])), "marked at last closed bar"),
        c.metric("Net P&L", c.money(_usd(a["pnl"]), signed=True), "since deploy · no fees"),
        c.metric(
            "Allocated", c.money(_usd(a["allocated"])), f"{len(a['deployments'])} deployments"
        ),
        c.metric(
            "Orders", f'<span class="num">{a["orders"]}</span>', "simulated fills at bar close"
        ),
    ]
    return f'<section class="strip" aria-label="Account metrics" data-financial="true">{"".join(cells)}</section>'


def render(
    lg: L.Ledger,
    *,
    start: str,
    now: float | None = None,
    account: str | None = None,
    status: str | None = None,
    view: str | None = None,
    workers: dict[str, dict] | None = None,
    supervisor_down: bool = False,
    studio: S.Studio | None = None,
    quality: D.Quality | None = None,
    registry: Registry | None = None,
    harness: dict | None = None,
    tickets: list[T.Parent] | None = None,
    ticket_msg: str | None = None,
    templates: list[dict] | None = None,
    template_workers: dict[str, dict] | None = None,
) -> str:
    """``lg`` must already be narrowed to the caller's grants (``demo.scope``)."""
    from algobots.demo import studio_page as SP  # imports this module
    from algobots.engine.workers import template as TPL

    now = time.time() if now is None else now
    studio = studio or S.load("/nonexistent")  # built-ins only
    quality = quality or D.quality(D.records(lg), lg, accounts=lg.books)
    account, status, view = B.account_key(account), B.status_key(status), view_key(view)
    if account not in lg.books and account not in (B.ALL, *B.EQUITY):
        account = B.ALL  # routes 403 first; this only guards direct callers
    workers = workers or {}
    templates, tw = templates or [], template_workers or {}
    vis = S.visible(tuple(lg.books))
    tpl = TPL.summary(studio, templates, now)
    tpos = TPL.positions(studio, templates, now, account)

    if account in B.EQUITY:
        ctx = f"ctx: {_ctx_label(account)}"
        accounts = c.panel(
            "Accounts",
            _accounts(lg, now, account, workers, registry, _eq_rows(tpl, account, tw))
            + "<h3>Deployments by account · frozen params + artifact</h3>"
            + SP.deployments(studio, account, vis, orders=templates, workers=tw),
            financial=True,
            tag=TAG,
            cls="full",
        )
        orders = c.panel(
            "Orders", _orders(lg, account, status, templates), financial=True, tag=ctx, cls="full"
        )
        strategies = c.panel(
            "Strategies",
            SP.strategies(studio, vis)
            + '<p class="meta"><a href="/demo/studio">studio: deploy a version with allocation preview →</a></p>',
            financial=True,
            tag="TEMPLATES: TEST ONLY",
            cls="full",
        )
        body = (
            _eq_stateline(tpl.get(account), account, tw)
            + _eq_strip(tpl.get(account))
            + _switcher(lg, account, view)
            + '<div class="grid">'
            + accounts
            + c.panel("Positions", _tpl_positions(tpos), financial=True, tag=ctx, cls="full")
            + orders
            + strategies
            + "</div>"
        )
    else:
        content = (
            _overview(lg, now, account, start, quality, workers, registry, supervisor_down)
            if view == "overview"
            else _tab(
                view,
                lg,
                now,
                account,
                status,
                studio,
                quality,
                workers,
                registry,
                Q.quality(lg, account=account) if harness is None else harness,
                tickets or [],
                ticket_msg,
                templates,
                tw,
            )
        )
        body = (
            _stateline(lg, now, account, supervisor_down)
            + _switcher(lg, account, view)
            + _tabs(account, view, registry)
            + f'<div class="view" data-view="{view}">{content}</div>'
        )
    title = "AlgoBots — paper trading dashboard"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta http-equiv="refresh" content="60">\n'
        f'<title>{title}</title>\n<style>{CSS}</style>\n</head>\n<body class="dash">\n'
        f'<div class="chrome">{_header(lg, now, account)}{_banner(lg, start)}</div>\n'
        f'<main id="main" data-screen="demo" data-account="{account}" data-view="{view}">\n<h1 class="sr-only">{title}</h1>\n{body}\n</main>\n'
        f"<script>{CLOCK}{KEYS}{HOVER}</script>\n</body>\n</html>\n"
    )
