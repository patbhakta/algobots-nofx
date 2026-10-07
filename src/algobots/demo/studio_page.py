# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Strategy studio views: the Strategies pane, deployments by account, deploy + preview page."""

from __future__ import annotations

import time
import typing
from decimal import Decimal
from urllib.parse import urlencode

from algobots.dashboard.design import components as c
from algobots.demo import ledger as L
from algobots.demo import page as P
from algobots.demo import studio as S
from algobots.demo.theme import CLOCK, CSS


def _type(definition: str, key: str) -> str:
    model = S.DEFINITIONS[definition].params
    if model is None:
        return "fixed"
    ann = model.model_fields[key].annotation
    if typing.get_origin(ann) is typing.Literal:
        return "enum"
    return getattr(typing.get_origin(ann) or ann, "__name__", "str")


def _val(v: object) -> str:
    if isinstance(v, dict):
        return ",".join(f"{k}={w:g}" for k, w in v.items())
    return f"{v:g}" if isinstance(v, float) else str(v)


def params_html(definition: str, params: dict) -> str:
    return " ".join(
        f'<span class="kv"><span class="meta">{c.e(k)}:{_type(definition, k)}=</span>{c.e(_val(v))}</span>'
        for k, v in params.items()
    )


def _hash(h: str) -> str:
    return f'<code class="num" title="sha256 {c.e(h)}">{c.e(h[:12])}</code>'


def strategies(st: S.Studio, visible: set[str] | None = None) -> str:
    """Every StrategyDefinition × Version with typed params and its frozen artifact hash."""
    rows = []
    order = list(S.DEFINITIONS)
    for v in sorted(st.versions, key=lambda v: (order.index(v.definition), -v.version)):
        d = S.DEFINITIONS[v.definition]
        live = d.kind == "live"
        if live and visible is not None and v.definition not in visible:
            continue  # an ungranted sleeve's strategy never leaves the server
        n = sum(
            1
            for x in st.deployments
            if x.hash == v.hash and (visible is None or x.account in visible)
        )
        rows.append(
            [
                f"<strong>{c.e(d.name)}</strong>",
                f'<span class="num">v{v.version}</span>'
                + (
                    ""
                    if v.hash != st.latest(v.definition).hash
                    else ' <span class="meta">latest</span>'
                ),
                c.e(d.kind),
                c.e(d.venue),
                params_html(v.definition, v.params),
                _hash(v.hash),
                c.status("connected", d.label) if live else c.status("stale", d.label),
                f'<span class="num">{n}</span>',
                NONE
                if live
                else f'<a href="/demo/studio?{c.e(urlencode({"version": v.short}))}">deploy →</a>',
            ]
        )
    return c.table(
        ["Strategy", "Ver", "Kind", "Venue", "Parameters", "Artifact", "Label", "Deps", ""],
        rows,
        numeric={7},
        stack=True,
    )


NONE = P.NONE


def deployments(
    st: S.Studio,
    account: str | None = None,
    visible: set[str] | None = None,
    *,
    orders: list[dict] | None = None,
    workers: dict[str, dict] | None = None,
) -> str:
    """Deployments grouped by account — each row is one frozen (version, account) instance.

    ``orders``/``workers``: template orders and template-worker states (ALG-3281), so each
    row shows how many orders carry its id and whether its worker is up."""
    orders, workers = orders or [], workers or {}
    count: dict[str, int] = {}
    for o in orders:
        count[o["deployment"]] = count.get(o["deployment"], 0) + 1
    deps = sorted(
        (
            d
            for d in st.deployments
            if account in (None, "all", d.account) and (visible is None or d.account in visible)
        ),
        key=lambda d: (list(S.ACCOUNTS).index(d.account), d.created_ts),
    )
    rows = [
        [
            c.e(S.ACCOUNTS[d.account].label),
            f'<span class="num">{c.e(d.id)}</span>',
            f"{c.e(S.DEFINITIONS[d.definition].name)} v{d.version}",
            _hash(d.hash),
            params_html(d.definition, d.params),
            c.money(P._usd(d.allocation)),
            f'<span class="num">{count.get(d.id, 0)}</span>' if d.actor != "built-in" else NONE,
            _run(d, workers.get(d.id)),
        ]
        for d in deps
    ]
    return c.table(
        [
            "Account",
            "Deployment",
            "Strategy",
            "Artifact",
            "Frozen params",
            "Alloc.",
            "Orders",
            "Run",
        ],
        rows,
        numeric={5, 6},
        stack=True,
        empty="No deployments.",
    )


def _run(d: S.Deployment, w: dict | None) -> str:
    """Recorded state (flipped by the supervisor on first ready heartbeat) + live worker."""
    if d.actor == "built-in":
        return c.status("connected", "RUNNING")
    ws = (w or {}).get("state")
    if d.state == "running":
        if ws in (None, "ready"):
            return c.status("connected", "RUNNING")
        return c.status("BLOCKED" if ws == "exited" else "stale", f"RUNNING · WORKER {ws.upper()}")
    if ws:
        return c.status("stale", f"PENDING · WORKER {ws.upper()}")
    return c.status("stale", "PENDING · NO WORKER")


def _form(st: S.Studio, q: dict, visible: set[str] | None) -> str:
    v = st.by_hash(q.get("version") or "") or st.latest("trend")
    opts = "".join(
        f'<option value="{x.short}"{" selected" if x.hash == v.hash else ""}>'
        f"{c.e(S.DEFINITIONS[x.definition].name)} v{x.version} · {x.short}</option>"
        for x in st.versions
        if S.DEFINITIONS[x.definition].kind != "live"
    )
    chosen = set(q.get("accounts") or [])
    accts = "".join(
        f'<label class="chk"><input type="checkbox" name="accounts" value="{a.id}"'
        f"{' checked' if a.id in chosen else ''}> {c.e(a.label)} "
        f'<span class="meta">{a.venue} · approved {a.approved} · free {max(Decimal(0), a.approved - st.committed(a.id))}</span></label>'
        for a in S.ACCOUNTS.values()
        if visible is None or a.id in visible
    )
    mode = q.get("mode") or "equal"
    radio = "".join(
        f'<label class="chk"><input type="radio" name="mode" value="{m}"{" checked" if m == mode else ""}> {lbl}</label>'
        for m, lbl in (("equal", "equal dollars"), ("pct", "% of approved"))
    )
    return (
        '<form method="get" action="/demo/studio" class="studio-form">'
        f'<label class="row"><span class="meta">Version</span><select name="version">{opts}</select></label>'
        f'<fieldset class="row"><legend class="meta">Accounts</legend>{accts}</fieldset>'
        f'<fieldset class="row"><legend class="meta">Sizing</legend>{radio}'
        f'<label class="chk">total USD <input name="amount" inputmode="decimal" size="8" value="{c.e(q.get("amount") or "")}"></label>'
        f'<label class="chk">% <input name="pct" inputmode="decimal" size="4" value="{c.e(q.get("pct") or "")}"></label></fieldset>'
        '<button type="submit" class="action">Preview allocation</button></form>'
    )


def _preview(pv: S.Preview, q: dict, kill: bool) -> str:
    rows = [
        [
            c.e(ln.label),
            c.money(P._usd(ln.approved)),
            c.money(P._usd(ln.available)),
            c.money(P._usd(ln.allocation)) if not ln.skip else NONE,
            c.money(P._usd(ln.residual)),
            c.status("ready", "DEPLOY") if not ln.skip else c.status("BLOCKED", "SKIP"),
            f'<span class="meta">{c.e(ln.skip or "")}</span>',
        ]
        for ln in pv.lines
    ]
    sizing = (
        f"equal dollars · {pv.requested} USD total"
        if pv.mode == "equal"
        else f"{q.get('pct')}% of approved allocation"
    )
    summary = (
        f'<p class="meta">{c.e(S.DEFINITIONS[pv.version.definition].name)} v{pv.version.version} · '
        f"artifact {pv.version.short} · {c.e(sizing)} · requested {pv.requested} · "
        f"allocated {pv.allocated} · undeployed {pv.undeployed} USD</p>"
    )
    hidden = "".join(
        f'<input type="hidden" name="{k}" value="{c.e(v)}">'
        for k, vs in q.items()
        for v in (vs if isinstance(vs, list) else [vs])
        if v
    )
    n = len(pv.deployable)
    button = (
        f'<form method="post" action="/demo/studio/deploy" class="actions">{hidden}'
        '<label class="field"><span class="sr-only">Your name for the audit log</span>'
        '<input name="actor" maxlength="40" placeholder="your name (audit log)"></label>'
        f'<button type="submit" class="action" data-environment="PAPER"><span>Create {n} paper deployment{"s" if n != 1 else ""}</span>'
        '<span class="ctx">frozen params · PAPER</span></button></form>'
        if n and not kill
        else '<p class="meta">Nothing to deploy: every selected account is skipped.</p>'
    )
    return (
        summary
        + c.table(
            ["Account", "Approved", "Free", "Allocation", "Residual", "Action", "Reason"],
            rows,
            numeric={1, 2, 3, 4},
            stack=True,
        )
        + button
    )


def _edit(st: S.Studio, q: dict) -> str:
    v = st.by_hash(q.get("version") or "") or st.latest("trend")
    if S.DEFINITIONS[v.definition].params is None:
        return ""
    inputs = "".join(
        f'<label class="chk">{c.e(k)}:{_type(v.definition, k)} '
        f'<input name="p_{c.e(k)}" value="{c.e(_val(val))}" size="{max(4, len(_val(val)) + 1)}"></label>'
        for k, val in v.params.items()
    )
    return (
        f"<h3>Edit template · new version of {c.e(S.DEFINITIONS[v.definition].name)}</h3>"
        f'<form method="post" action="/demo/studio/edit" class="studio-form">'
        f'<input type="hidden" name="definition" value="{v.definition}">'
        f'<div class="row">{inputs}</div>'
        '<button type="submit" class="action">Save as new version</button>'
        '<span class="meta"> running deployments keep their frozen copy</span></form>'
    )


def render_studio(
    st: S.Studio,
    lg: L.Ledger,
    *,
    start: str,
    q: dict,
    pv: S.Preview | None = None,
    error: str | None = None,
    flash: str | None = None,
    now: float | None = None,
    visible: set[str] | None = None,
) -> str:
    now = time.time() if now is None else now
    kill = bool(lg.kill.get("engaged"))
    msg = (
        f'<p class="flash err" role="alert">✕ {c.e(error or flash)}</p>'
        if error or " refused: " in (flash or "")
        else f'<p class="flash" role="status">{c.e(flash)}</p>'
        if flash
        else ""
    )
    deploy_body = _form(st, q, visible) + (_preview(pv, q, kill) if pv else "") + _edit(st, q)
    body = (
        msg
        + '<div class="grid">'
        + c.panel(
            "Strategies",
            strategies(st, visible),
            financial=True,
            tag="TEMPLATES: TEST ONLY",
            cls="full",
        )
        + c.panel(
            "Deploy · allocation preview", deploy_body, financial=True, tag="PAPER", cls="full"
        )
        + c.panel(
            "Deployments by account",
            deployments(st, visible=visible),
            financial=True,
            tag="FROZEN",
            cls="full",
        )
        + "</div>"
    )
    title = "AlgoBots — strategy studio"
    return (
        '<!doctype html>\n<html lang="en">\n<head>\n'
        '<meta charset="utf-8">\n<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{title}</title>\n<style>{CSS}</style>\n</head>\n<body>\n"
        f'<div class="chrome">{P._header(lg, now, "all")}'
        '<div class="disclosure" role="note"><strong>STRATEGY STUDIO</strong>'
        '<a href="/demo">← terminal</a>'
        "<span>templates are test strategies with no validated returns</span>"
        '<span class="wide">deployments freeze params + artifact hash · template runner not yet live: new deployments place no orders</span></div></div>\n'
        f'<main id="main" data-screen="studio">\n<h1 class="sr-only">{title}</h1>\n{body}\n</main>\n'
        f"<script>{CLOCK}</script>\n</body>\n</html>\n"
    )
