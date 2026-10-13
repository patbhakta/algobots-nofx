# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Static, clickable fixture storyboard: 4 screens x 5 fixture states.

`build(out_dir)` writes `index.html` plus `<screen>-<state>.html` pages that
need no server, network or live service (open from disk). Output is
byte-for-byte deterministic. Pages render synthetic fixtures only and every
page carries the DEMO DATA banner; a fixture UI is not evidence of broker
integration.

Query parameter: `?audit=1`, which writes a layout-overflow report into
`#audit` for headless checks. There are no texture or motion settings: the
NoFX design language (ALG-3336) ships no effects to toggle.
"""

from decimal import Decimal
from pathlib import Path

from algobots.dashboard.design import components as c
from algobots.dashboard.design.css import stylesheet
from algobots.dashboard.fixtures import DEMO_LABEL, STATES, fixture

SCREENS = {
    "overview": "Overview",
    "workspace": "Advanced workspace",
    "studio": "Strategy studio",
    "invite": "Invitation & onboarding",
}

_SCRIPT = """
(function () {
  var q = new URLSearchParams(location.search);
  if (q.get("audit") === "1") {
    var w = window.innerWidth, over = [], clipped = [];
    document.querySelectorAll(".metric, .action, .badge, .status").forEach(function (el) {
      if (el.scrollWidth > el.clientWidth + 1) clipped.push(el.className + ":" + el.textContent.trim().slice(0, 24));
    });
    document.querySelectorAll("body *").forEach(function (el) {
      var b = el.getBoundingClientRect();
      if (b.width && b.right > w + 1 && !el.closest(".body")) {
        over.push((el.className || el.tagName) + "@" + Math.round(b.right));
      }
    });
    var pre = document.createElement("pre");
    pre.id = "audit";
    pre.textContent = JSON.stringify({
      innerWidth: w, scrollWidth: document.documentElement.scrollWidth,
      overflowing: over.slice(0, 20), clipped: clipped.slice(0, 20)
    });
    document.body.appendChild(pre);
  }
})();
"""


def _account(f: dict, account_id: str | None = None) -> dict:
    wanted = account_id or f["account_id"]
    return next(a for a in f["accounts"] if a["id"] == wanted)


def _age(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _paused(f: dict) -> str | None:
    if f["feed"]["status"] != "connected":
        return f"Paused: market data {_age(f['feed']['age_s'])} old"
    if f["feed"]["reconciliation"] == "reconciling":
        return "Paused: reconciling broker state"
    return None


def _act(f: dict, label: str, *, account_id: str | None = None, reason: str | None = None) -> str:
    if account_id and not any(a["id"] == account_id for a in f["accounts"]):
        return ""  # account not in this fixture's scope
    acct = _account(f, account_id)
    if acct["environment"] == "LIVE":
        reason = "Live trading not authorized (demo)"
    return c.action(label, account=acct, environment=acct["environment"], disabled_reason=reason)


def _header(f: dict) -> str:
    acct = _account(f)
    feed, recon = f["feed"], f["feed"]["reconciliation"]
    feed_status = c.status(
        feed["status"] if feed["status"] != "connected" or feed["age_s"] < 60 else "stale",
        f"data {feed['status']} · {_age(feed['age_s'])}",
    )
    recon_status = c.status(recon, f"reconciliation {recon} · {_age(feed['recon_age_s'])}")
    approvals = f["pending_approvals"]
    return (
        '<header class="app-header">'
        f'<span class="crumb wide">{c.e(f["workspace"])}</span>'
        '<span class="wide" aria-hidden="true">→</span>'
        f'<span class="crumb" data-account="{c.e(acct["id"])}">{c.e(acct["label"])}</span>'
        f"{c.env_badge(acct['environment'])}"
        f'<span class="meta wide">{c.e(acct["broker"])} · {c.e(acct["currency"])}</span>'
        f"{feed_status}{recon_status}"
        f'<span class="meta">{approvals} pending approval{"s" if approvals != 1 else ""}</span>'
        "</header>"
    )


def _nav(screen: str, state: str) -> str:
    screens = "".join(
        f'<a href="{s}-{state}.html"{" aria-current=page" if s == screen else ""}>{c.e(t)}</a>'
        for s, t in SCREENS.items()
    )
    states = "".join(
        f'<a href="{screen}-{s}.html"{" aria-current=page" if s == state else ""}>{s}</a>'
        for s in STATES
    )
    return (
        f'<nav class="screens" aria-label="Screens">{screens}<a href="index.html">All pages</a>'
        f'<span class="spacer"></span></nav>'
        f'<nav class="screens states" aria-label="Fixture state">'
        f'<span class="meta">fixture:</span>{states}</nav>'
    )


def _banner(f: dict) -> str:
    return (
        f'<div class="demo-banner" role="note"><strong>{DEMO_LABEL}</strong>'
        f"<span>fixture “{c.e(f['state'])}”</span>"
        '<span class="wide">synthetic · not broker data · not investment evidence</span>'
        f'<span class="meta wide">as of {c.e(f["as_of"])}</span></div>'
    )


def _portfolio_strip(f: dict, *, compact: bool = False) -> str:
    p, acct = f["portfolio"], _account(f)
    asof = f"as of {f['as_of'][11:16]}Z · {acct['currency']}"
    reason = p.get("valuation_unavailable_reason", "not available")
    cells = [
        c.metric("Equity", c.money(p["equity"], reason=reason), asof, compact=compact),
        c.metric(
            "Net P&L",
            c.money(p["net_pnl"], signed=True, reason=reason),
            f"{f['period']} · excl. cash flows",
            compact=compact,
        ),
        c.metric(
            "Return",
            c.pct(p["net_pnl_pct"], signed=True, reason=reason),
            "time-weighted, net of fees",
            compact=compact,
        ),
        c.metric("Available cash", c.money(p["available_cash"]), "settled", compact=compact),
        c.metric("Reserved cash", c.money(p["reserved_cash"]), "working orders", compact=compact),
        c.metric("Exposure", c.pct(p["exposure_pct"]), "gross / equity", compact=compact),
        c.metric(
            "Open positions",
            f'<span class="num" data-fin="count">{p["open_positions"]}</span>',
            "this account",
            compact=compact,
        ),
        c.metric(
            "Drawdown",
            c.pct(p["drawdown_pct"], signed=True, reason=reason),
            "from period high",
            compact=compact,
        ),
    ]
    strip = "".join(cells)
    return f'<section class="strip" aria-label="Portfolio metrics" data-financial="true">{strip}</section>'


def _stats_strip(f: dict) -> str:
    s = f["stats"]
    kw = {"sample": s["sample"], "period": f["period"], "costs": s["costs_included"]}
    return (
        '<section class="strip advanced" aria-label="Strategy statistics" data-financial="true">'
        + c.stat("Win rate", s["win_rate_pct"], unit="%", **kw)
        + c.stat("Profit factor", s["profit_factor"], **kw)
        + c.stat("Trades", s["trades"], **kw)
        + c.stat("Sharpe", s["sharpe"], **kw)
        + c.stat("Avg win", s["avg_win"], unit=" USD", **kw)
        + c.stat("Avg loss", s["avg_loss"], unit=" USD", **kw)
        + "</section>"
    )


def _positions(f: dict) -> str:
    rows = [
        [
            c.e(p["symbol"]),
            c.e(p["venue"]),
            f'<span class="num">{c.e(p["qty"])}</span>',
            c.money(p["cost"]),
            c.money(p["value"]),
            c.money(p["pnl"], signed=True),
        ]
        for p in f["positions"]
    ]
    return c.table(
        ["Symbol", "Venue", "Qty", "Cost basis", "Value", "Unrealized"],
        rows,
        numeric={2, 3, 4, 5},
        empty="No open positions. This account has not traded yet.",
    )


def _exceptions(f: dict) -> str:
    kinds = {
        "partial_fill": "PARTIALLY_FILLED",
        "drawdown": "REJECTED",
        "stale": "stale",
        "unknown": "UNKNOWN",
    }
    if not f["exceptions"]:
        return '<p class="empty">No exceptions.</p>'
    return (
        '<ul class="steps">'
        + "".join(
            f"<li><span>{c.e(x['text'])}</span>"
            f"{c.status(kinds[x['kind']], x['kind'].replace('_', ' '))}</li>"
            for x in f["exceptions"]
        )
        + "</ul>"
    )


def _orders(f: dict, *, with_actions: bool) -> str:
    rows = []
    for o in f["orders"]:
        filled = "unknown" if o["filled"] is None else f"{o['filled']}/{o['qty']}"
        row = [
            f'<span class="num">{c.e(o["id"])}</span>',
            c.e(o["symbol"]),
            c.e(o["side"]),
            f'<span class="num">{c.e(filled)}</span>',
            c.money(o["limit"]),
            c.status(o["status"])
            + (f'<div class="meta">{c.e(o["reason"])}</div>' if o.get("reason") else ""),
        ]
        if with_actions:  # cancel stays available while data is stale or state unknown
            if o["status"] == "PARTIALLY_FILLED":
                row.append(_act(f, f"Cancel {o['id']}"))
            elif o["status"] == "UNKNOWN":
                row.append(_act(f, f"Request cancel {o['id']}"))
            else:
                row.append("")
        rows.append(row)
    headers = ["Order", "Symbol", "Side", "Filled", "Limit", "Status"] + (
        ["Action"] if with_actions else []
    )
    return c.table(headers, rows, numeric={3, 4}, empty="No orders yet.")


def _topology(f: dict) -> str:
    if not f["topology"]:
        return '<p class="empty">No events yet. The trail appears when a strategy evaluates.</p>'
    out = []
    for t in f["topology"]:
        nodes = ' <span class="edge" aria-hidden="true">→</span> '.join(
            f'<span class="node">{c.e(n)}</span>' for n in t["path"]
        )
        tail = " · hold, no execution" if t["outcome"] == "ABSTAIN" else ""
        out.append(
            f'<details class="explain"><summary class="trace" aria-label="Trace {c.e(t["trace"])} '
            f'{c.e(t["symbol"])} {c.e(t["outcome"])}">'
            f'<span class="num meta">{c.e(t["trace"])}</span> '
            f"<strong>{c.e(t['symbol'])}</strong> {nodes} {c.status(t['outcome'])}"
            f'<span class="meta">{tail}</span></summary>'
            f"<p>Reason: {c.e(t['reason'])}</p>"
            f'<p class="meta">Inputs, sources and outcome load from the trace record '
            f"(fixture: reason only).</p></details>"
        )
    return '<div class="topology">' + "".join(out) + "</div>"


def _depth(f: dict) -> str:
    d = f["depth"]
    if not d["entitled"]:
        return f'<p class="empty">{c.status("not_granted", "Unsupported")} {c.e(d["reason"])}.</p>'
    peak = max(Decimal(q) for _, q in d["bids"] + d["asks"])
    rows = []
    for (bp, bq), (ap, aq) in zip(d["bids"], d["asks"], strict=True):
        rows.append(
            [
                c.bar(float(Decimal(bq) / peak), label=f"bid {bq} at {bp}", cls="bid"),
                f'<span class="num">{bq}</span>',
                f'<span class="num pos">{bp}</span>',
                f'<span class="num neg">{ap}</span>',
                f'<span class="num">{aq}</span>',
                c.bar(float(Decimal(aq) / peak), label=f"ask {aq} at {ap}", cls="ask"),
            ]
        )
    stale = (
        f'<p class="meta attn">{c.status("stale", "snapshot stale — resync pending")}</p>'
        if d.get("stale")
        else ""
    )
    return (
        stale
        + f'<p class="meta">{c.e(d["symbol"])} · {c.e(d["venue"])} · L2</p><div class="depth">'
        + c.table(["", "Bid qty", "Bid", "Ask", "Ask qty", ""], rows, numeric={1, 2, 3, 4})
        + "</div>"
    )


def _cost_distribution(f: dict) -> str:
    dist = f["cost_distribution"]
    if not dist:
        return '<p class="empty">No owned exposure.</p>'
    peak = max(Decimal(b["qty"]) for b in dist)
    rows = [
        [
            c.e(b["bucket"]),
            f'<span class="num">{c.e(b["qty"])}</span>',
            c.bar(
                float(Decimal(b["qty"]) / peak), label=f"{b['qty']} shares bought at {b['bucket']}"
            ),
        ]
        for b in dist
    ]
    return (
        '<p class="meta">SPY owned shares by cost basis (USD). No liquidation estimates: '
        "no qualified source.</p>" + c.table(["Cost band", "Qty", ""], rows, numeric={1})
    )


def _signals(f: dict) -> str:
    rows = [
        [
            c.e(s["strategy"]),
            c.e(s["symbol"]),
            c.status(s["state"]),
            f'<span class="num">{c.e(s["version"])}</span>',
            "yes" if s["eligible"] else "no",
            f'<span class="num">{c.e(s["evaluated"])}</span>',
        ]
        for s in f["signals"]
    ]
    return c.table(
        ["Strategy", "Instr.", "State", "Version", "Eligible", "Last eval"],
        rows,
        empty="No deployed strategies.",
    )


def _candles(f: dict) -> str:
    k = f["candles"]
    meta = (
        f"{c.e(k['symbol'])} · {c.e(k['venue'])} · {c.e(k['timeframe'])} · {c.e(k['timezone'])} · "
        f"warmup {'complete' if k['warmup_complete'] else 'incomplete'}"
    )
    if not k["bars"]:
        return f'<p class="meta">{meta}</p><p class="empty">No bars: warmup incomplete, no history loaded.</p>'
    lows = [Decimal(b[2]) for b in k["bars"]]
    highs = [Decimal(b[1]) for b in k["bars"]]
    lo, hi = min(lows), max(highs)
    span, step, h = hi - lo or Decimal(1), 14, 150

    def y(v: str) -> str:
        return f"{float((hi - Decimal(v)) / span * h) + 5:.1f}"

    parts = []
    for i, (o, hgh, low, cl) in enumerate(k["bars"]):
        x = 20 + i * step
        up = Decimal(cl) >= Decimal(o)
        color = "var(--c-positive)" if up else "var(--c-negative)"
        top, bottom = (cl, o) if up else (o, cl)
        height = max(1.0, float(y(bottom)) - float(y(top)))
        parts.append(
            f'<line x1="{x}" x2="{x}" y1="{y(hgh)}" y2="{y(low)}" stroke="{color}" stroke-width="1" vector-effect="non-scaling-stroke"/>'
            f'<rect x="{x - 4}" y="{y(top)}" width="8" height="{height:.1f}" '
            f'fill="{"none" if up else color}" stroke="{color}" stroke-width="1" vector-effect="non-scaling-stroke"/>'
        )
    gap = (
        f'<p class="meta attn">{c.status("stale", "data gap: bars after last update missing")}</p>'
        if k["gap"]
        else ""
    )
    width = 30 + len(k["bars"]) * step
    return (
        f'<p class="meta">{meta}</p>{gap}<div class="candles">'
        f'<svg viewBox="0 0 {width} 160" preserveAspectRatio="none" role="img" '
        f'aria-label="{c.e(k["symbol"])} {c.e(k["timeframe"])} candles, low {lo}, high {hi}">'
        f'<line x1="0" x2="{width}" y1="155" y2="155" stroke="var(--c-rule-faint)"/>{"".join(parts)}</svg></div>'
    )


def _scope(f: dict) -> str:
    rows = []
    for a in f["accounts"]:
        bal = ""
        sb = f.get("secondary_balance")
        if a["id"] == f["account_id"]:
            bal = c.money(
                f["portfolio"]["equity"],
                reason=f["portfolio"].get("valuation_unavailable_reason", "not available"),
            )
        elif sb and a["id"] == sb["account_id"]:
            bal = c.money(sb["equity"])
        else:
            bal = '<span class="meta">not shown: no grant</span>'
        rows.append([c.e(a["label"]), c.env_badge(a["environment"]), c.e(a["currency"]), bal])
    return c.table(["Account", "Mode", "Ccy", "Equity"], rows, numeric={3}) + (
        '<p class="meta">Mixed currencies are shown in their own currency, not converted.</p>'
        if len(f["accounts"]) > 1
        else ""
    )


def _cashflow(f: dict) -> str:
    p = f["portfolio"]
    rows = [
        ["Net P&L (excl. cash flows)", c.money(p["net_pnl"], signed=True)],
        ["Deposits", c.money(p["deposits"])],
        ["Withdrawals", c.money(p["withdrawals"])],
        ["Fees", c.money(p["fees"])],
    ]
    return c.table(["", f"{f['period']}"], rows, numeric={1})


def _allocation(f: dict) -> str:
    rows = [
        [
            c.e(a["strategy"]),
            c.money(a["capital"]),
            f'<span class="num">{c.e(a["weight_pct"])}%</span>',
        ]
        for a in f["allocation"]
    ]
    return c.table(
        ["Sleeve", "Capital", "Weight"], rows, numeric={1, 2}, empty="No capital allocated."
    )


def screen_overview(f: dict) -> str:
    paused = _paused(f)
    queue = []
    if f["pending_approvals"]:
        queue.append(_act(f, "Approve QQQ buy 10 @ 504.10", reason=paused))
        queue.append(_act(f, "Reject QQQ buy 10 @ 504.10"))
    queue.append(_act(f, "Pause all strategies"))
    queue.append(_act(f, "Resume trading", account_id="demo-acct-003"))
    return (
        _portfolio_strip(f)
        + '<div class="cols">'
        + c.panel("Scope", _scope(f), financial=True)
        + c.panel("Performance and cash flows", _cashflow(f), financial=True)
        + c.panel("Allocation", _allocation(f), financial=True)
        + "</div>"
        + '<div class="cols two">'
        + c.panel("Open positions", _positions(f), financial=True)
        + c.panel(
            "Exceptions and action queue",
            _exceptions(f) + f'<div class="actions">{"".join(queue)}</div>',
            raised=True,
        )
        + "</div>"
    )


def screen_workspace(f: dict) -> str:
    return (
        _portfolio_strip(f, compact=True)
        + _stats_strip(f)
        + '<div class="cols">'
        + c.panel("Cost-basis distribution", _cost_distribution(f), financial=True)
        + c.panel("Order book", _depth(f), financial=True, cls="advanced")
        + c.panel("Signal matrix", _signals(f))
        + "</div>"
        + c.panel("Candles", _candles(f), financial=True, cls="advanced")
        + c.panel("Event topology", _topology(f))
        + '<div class="cols two">'
        + c.panel("Recent orders", _orders(f, with_actions=True), financial=True)
        + c.panel(
            "Exceptions",
            _exceptions(f) + '<div class="actions">' + _act(f, "Pause Momentum v3") + "</div>",
            raised=True,
        )
        + "</div>"
    )


def screen_studio(f: dict) -> str:
    st = f["studio"]
    templates = (
        '<ul class="steps">'
        + "".join(
            f"<li><span>{c.e(t)}</span>"
            f"{c.status('ready', 'selected') if t == st['selected'] else ''}</li>"
            for t in st["templates"]
        )
        + "</ul>"
    )
    fields = "".join(c.field(p["name"], p["value"], p["unit"], p["error"]) for p in st["params"])
    scope = (
        f'<p class="meta">Version {c.e(st["version"])} active · editing {c.e(st["draft_version"])}. '
        "Edits never change the active deployment; a new approved version is required.</p>"
        f'<p class="meta">Universe: {c.e(st["universe"])} · warmup {c.e(st["warmup"])} · '
        f"capital {c.money(st['capital'])} · scope: owned positions in this sleeve</p>"
    )
    pipe = st["pipeline"]
    steps = (
        '<ul class="steps">'
        + "".join(
            f"<li><span>{c.e(n)}</span>{c.status(pipe[k])}</li>"
            for k, n in (
                ("draft", "Save draft"),
                ("validate", "Validate"),
                ("backtest", "Backtest"),
                ("paper_deploy", "Paper deploy"),
                ("live_review", "Live review (optional)"),
            )
        )
        + "</ul>"
    )
    invalid = any(p["error"] for p in st["params"])
    actions = (
        '<div class="actions">'
        + "".join(
            [
                _act(f, "Save draft"),
                _act(f, "Validate"),
                _act(f, "Run backtest", reason="Fix invalid fields first" if invalid else None),
                _act(
                    f,
                    "Deploy to paper",
                    reason="Fix invalid fields first"
                    if invalid
                    else ("Run a backtest first" if pipe["backtest"] != "done" else _paused(f)),
                ),
                _act(f, "Request live review", account_id="demo-acct-003"),
            ]
        )
        + "</div>"
    )
    r = st["results"]
    if r:
        results = (
            c.table(
                ["Measure", "Value"],
                [
                    ["Kind", c.e(r["kind"])],
                    ["Period", c.e(r["period"])],
                    ["CAGR", c.pct(r["cagr_pct"], signed=True)],
                    ["Max drawdown", c.pct(r["max_dd_pct"], signed=True)],
                    ["Trades", f'<span class="num">{c.e(r["trades"])}</span>'],
                    ["Costs", c.e(r["costs"])],
                    ["Benchmark", c.e(r["benchmark"])],
                ],
                numeric={1},
            )
            + '<p class="meta">Backtest is a hypothesis, not a paper or live observation.</p>'
        )
    else:
        results = (
            '<p class="empty">No results yet. Validate and backtest a draft to see evidence.</p>'
        )
    return (
        '<div class="cols">'
        + c.panel("Template library", templates)
        + c.panel(
            "Rules and parameters", scope + fields + steps + actions, raised=True, financial=True
        )
        + c.panel("Test and evidence", results, financial=True)
        + "</div>"
    )


def screen_invite(f: dict) -> str:
    inv = f["invite"]
    acct = _account(f, inv["account_id"])
    steps = [
        ("Single-use invite", f'<span class="num">{c.e(inv["code_hint"])}</span>', inv["status"]),
        (
            "Account identity",
            f"{c.e(acct['label'])} · {c.e(acct['broker'])} {c.env_badge(acct['environment'])}",
            "ready",
        ),
        (
            "Membership",
            f"role {c.e(inv['role'])} · trade permission {'yes' if inv['trade_permission'] else 'no'}",
            inv["status"],
        ),
        ("MFA enrollment (optional)", "", inv["mfa"]),
        ("Paper setup", "", inv["paper_setup"]),
    ]
    body = (
        '<ul class="steps">'
        + "".join(
            f"<li><span><strong>{c.e(n)}</strong> {d}</span>{c.status(s)}</li>" for n, d, s in steps
        )
        + "</ul>"
    )
    caps = (
        '<ul class="steps">'
        + "".join(
            f"<li><span>{c.e(x['name'])}</span>{c.status(x['status'])}</li>"
            for x in inv["capabilities"]
        )
        + "</ul>"
    )
    reason = {
        "expired": "Invite expired: ask the operator for a new one",
        "accepted": "Already accepted",
    }.get(inv["status"])
    actions = (
        '<div class="actions">'
        + _act(f, "Accept invitation", account_id=acct["id"], reason=reason)
        + (
            _act(f, "Enroll MFA", account_id=acct["id"])
            if inv["mfa"] == "optional" and inv["status"] != "expired"
            else ""
        )
        + "</div>"
    )
    note = (
        '<p class="meta">No public signup. Invited by '
        f"{c.e(inv['inviter'])}. An invite grants membership, not trade permission.</p>"
    )
    p = f["portfolio"]
    summary = c.table(
        ["", acct["currency"]],
        [
            [
                "Equity",
                c.money(p["equity"], reason=p.get("valuation_unavailable_reason", "not available")),
            ],
            ["Net P&L", c.money(p["net_pnl"], signed=True)],
        ],
        numeric={1},
    )
    return (
        '<div class="cols">'
        + c.panel("Join account", note + body + actions, raised=True)
        + c.panel("Capability status", caps)
        + c.panel("Account you are joining", summary, financial=True)
        + "</div>"
    )


RENDERERS = {
    "overview": screen_overview,
    "workspace": screen_workspace,
    "studio": screen_studio,
    "invite": screen_invite,
}


def page(screen: str, state: str) -> str:
    f = fixture(state)
    title = f"{SCREENS[screen]} — {state} — AlgoBots {DEMO_LABEL}"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{c.e(title)}</title>\n<style>\n{stylesheet()}</style>\n</head>\n<body>\n"
        f'<div class="chrome">{_banner(f)}{_header(f)}</div>\n{_nav(screen, state)}\n'
        f'<main id="main" data-screen="{screen}" data-state="{state}">\n'
        f'<h1 class="sr-only">{c.e(title)}</h1>\n{RENDERERS[screen](f)}\n</main>\n'
        f"<script>{_SCRIPT}</script>\n</body>\n</html>\n"
    )


def index() -> str:
    rows = "".join(
        f"<tr><td>{c.e(t)}</td>"
        + "".join(f'<td><a href="{s}-{st}.html">{st}</a></td>' for st in STATES)
        + "</tr>"
        for s, t in SCREENS.items()
    )
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>AlgoBots storyboard — {DEMO_LABEL}</title>\n<style>\n{stylesheet()}</style>\n</head>\n<body>\n"
        f'<div class="chrome"><div class="demo-banner" role="note"><strong>{DEMO_LABEL}</strong>'
        "<span>A09 fixture storyboard · synthetic data only · not broker integration evidence</span></div></div>\n"
        "<main><h1>AlgoBots NoFX storyboard</h1>"
        + c.panel(
            "Pages",
            '<table class="data"><thead><tr><th scope="col">Screen</th>'
            + "".join(f'<th scope="col">{s}</th>' for s in STATES)
            + f"</tr></thead><tbody>{rows}</tbody></table>",
        )
        + f"</main>\n<script>{_SCRIPT}</script>\n</body>\n</html>\n"
    )


def pages() -> dict[str, str]:
    out = {"index.html": index()}
    for s in SCREENS:
        for st in STATES:
            out[f"{s}-{st}.html"] = page(s, st)
    return out


def build(out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name, html in pages().items():
        path = out_dir / name
        path.write_text(html, encoding="utf-8")
        written.append(path)
    return written
