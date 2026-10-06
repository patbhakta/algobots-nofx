# ruff: noqa: E501  (HTML templates: markup fragments stay on one line)
"""Accessible status and layout components (server-rendered HTML strings).

Invariants enforced here, not by convention:

* `action()` refuses to render without an account and a PAPER/LIVE environment,
  and prints both inside the control, so every action shows its account context.
* `money()`/`stat()` render missing values as "Unavailable" with the reason;
  they never print a zero or infinity for an unknown value. Signs are explicit
  text (+ / −), so a value is readable without color.
* `status()` always pairs a glyph and a text label with an aria-label, so
  color is never the only signal.
* `panel(financial=True)` adds a visible DEMO DATA tag to the panel header.

All text is HTML-escaped.
"""

from decimal import Decimal
from html import escape

ENVIRONMENTS = ("PAPER", "LIVE")

# kind -> (css class, glyph); text label comes from the caller or the status name.
STATUS_STYLES = {
    "FILLED": ("ok", "✓"),
    "APPROVED": ("ok", "✓"),
    "ready": ("ok", "✓"),
    "done": ("ok", "✓"),
    "complete": ("ok", "✓"),
    "accepted": ("ok", "✓"),
    "enrolled": ("ok", "✓"),
    "connected": ("ok", "●"),
    "matched": ("ok", "✓"),
    "LONG": ("info", "▲"),
    "SHORT": ("info", "▼"),
    "PARTIALLY_FILLED": ("warn", "◐"),
    "AWAITING_APPROVAL": ("warn", "…"),
    "pending": ("warn", "…"),
    "todo": ("neutral", "○"),
    "optional": ("neutral", "○"),
    "stale": ("warn", "!"),
    "reconciling": ("warn", "↻"),
    "RECONCILING": ("warn", "↻"),
    "expired": ("warn", "!"),
    "REJECTED": ("bad", "✕"),
    "BLOCKED": ("bad", "✕"),
    "failed": ("bad", "✕"),
    "blocked": ("bad", "✕"),
    "disconnected": ("bad", "✕"),
    "ABSTAIN": ("neutral", "–"),
    "not_granted": ("neutral", "–"),
    "not_authorized": ("neutral", "–"),
    "UNKNOWN": ("warn", "?"),
    "unknown": ("warn", "?"),
}

INVENTORY = (
    ("demo_banner", "Sticky DEMO DATA banner on every storyboard page"),
    (
        "app_header",
        "Workspace, account, PAPER/LIVE badge, data/reconciliation freshness, approvals",
    ),
    ("env_badge", "PAPER/LIVE authority badge (text, not color alone)"),
    ("status", "Glyph + text + aria-label status chip for order/signal/topology/step states"),
    ("money", "Tabular currency value with explicit sign and Unavailable state"),
    ("metric", "KPI cell: label, tabular value, as-of/period/fees meta"),
    ("stat", "Advanced statistic with sample count, period, costs and Unavailable reason"),
    ("panel", "Thin-ruled panel with header; financial panels carry a DEMO DATA tag"),
    ("table", "Data table with right-aligned tabular numeric columns"),
    ("action", "Button that always shows account and environment; disabled state states why"),
    ("bar", "Thin horizontal bar for depth/cost distributions (real snapshot widths)"),
    ("trace", "Topology trail market → signal → risk → order → position with explain drawer"),
    ("field", "Typed parameter input with unit and field-level error"),
    ("settings", "Texture-off and motion-off toggles (persisted, URL-overridable)"),
)


def e(value: object) -> str:
    return escape("" if value is None else str(value), quote=True)


def env_badge(environment: str) -> str:
    if environment not in ENVIRONMENTS:
        raise ValueError(f"environment must be one of {ENVIRONMENTS}, got {environment!r}")
    label = "Paper trading account" if environment == "PAPER" else "Live trading account"
    return (
        f'<span class="badge env-{environment.lower()}" aria-label="{label}" '
        f'data-environment="{environment}">{environment}</span>'
    )


def status(kind: str, text: str | None = None) -> str:
    cls, glyph = STATUS_STYLES.get(kind, ("warn", "?"))
    label = text or kind.replace("_", " ").lower()
    return (
        f'<span class="status {cls}" role="status" aria-label="{e(label)}" data-status="{e(kind)}">'
        f'<span class="glyph" aria-hidden="true">{glyph}</span>{e(label)}</span>'
    )


def _unavailable(reason: str) -> str:
    return (
        f'<span class="num unavailable" data-fin="unavailable" title="{e(reason)}">'
        "Unavailable</span>"
    )


def _group(d: Decimal) -> str:
    places = max(0, -d.as_tuple().exponent)
    return f"{abs(d):,.{places}f}"


def money(m: dict | None, *, signed: bool = False, reason: str = "not available") -> str:
    if m is None:
        return _unavailable(reason)
    d = Decimal(m["amount"])
    cur = e(m["currency"])
    if not signed:
        sign = "−" if d < 0 else ""
        return f'<span class="num" data-fin="money">{sign}{_group(d)} <span class="ccy">{cur}</span></span>'
    if d > 0:
        cls, sign, word = "pos", "+", "gain"
    elif d < 0:
        cls, sign, word = "neg", "−", "loss"
    else:
        cls, sign, word = "", "", "flat"
    return (
        f'<span class="num {cls}" data-fin="money">{sign}{_group(d)} <span class="ccy">{cur}</span>'
        f'<span class="sr-only"> {word}</span></span>'
    )


def pct(value: str | None, *, signed: bool = False, reason: str = "not available") -> str:
    if value is None:
        return _unavailable(reason)
    d = Decimal(value)
    if not signed or d == 0:
        return f'<span class="num" data-fin="pct">{e(value)}%</span>'
    cls, sign = ("pos", "+") if d > 0 else ("neg", "−")
    return f'<span class="num {cls}" data-fin="pct">{sign}{abs(d)}%</span>'


def metric(label: str, value_html: str, meta: str = "", *, compact: bool = False) -> str:
    unavailable = "unavailable" if 'data-fin="unavailable"' in value_html else ""
    return (
        f'<div class="metric{" compact" if compact else ""}">'
        f'<div class="label">{e(label)}</div>'
        f'<div class="value {unavailable}">{value_html}</div>'
        f'<div class="meta">{e(meta)}</div></div>'
    )


def stat(label: str, s: dict, *, sample: int, period: str, costs: bool, unit: str = "") -> str:
    meta = f"n={sample} · {period} · {'net of costs' if costs else 'gross'}"
    if s["value"] is None:
        value = (
            f'<span class="num unavailable" data-fin="unavailable">Unavailable</span>'
            f'<span class="meta"> — {e(s["unavailable_reason"])}</span>'
        )
    else:
        value = f'<span class="num" data-fin="stat">{e(s["value"])}{e(unit)}</span>'
    return metric(label, value, meta, compact=True)


def panel(
    title: str,
    body: str,
    *,
    financial: bool = False,
    extra: str = "",
    raised: bool = False,
    cls: str = "",
) -> str:
    tag = '<span class="demo-tag">DEMO DATA</span>' if financial else ""
    classes = " ".join(c for c in ("panel", "raised" if raised else "", cls) if c)
    return (
        f'<section class="{classes}" data-financial="{str(financial).lower()}" '
        f'aria-label="{e(title)}">'
        f"<header><h2>{e(title)}</h2><span>{extra}{tag}</span></header>"
        f'<div class="body">{body}</div></section>'
    )


def table(
    headers: list[str],
    rows: list[list[str]],
    *,
    numeric: set[int] = frozenset(),
    empty: str = "Nothing to show yet.",
) -> str:
    if not rows:
        return f'<p class="empty">{e(empty)}</p>'
    th = "".join(
        f'<th scope="col"{" class=n" if i in numeric else ""}>{e(h)}</th>'
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(f"<td{' class=n' if i in numeric else ''}>{c}</td>" for i, c in enumerate(r))
        + "</tr>"
        for r in rows
    )
    return f'<table class="data"><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table>'


def action(
    label: str, *, account: dict | None, environment: str | None, disabled_reason: str | None = None
) -> str:
    if not account or not account.get("id") or not account.get("label"):
        raise ValueError(f"action {label!r} needs an account context")
    if environment not in ENVIRONMENTS:
        raise ValueError(f"action {label!r} needs environment PAPER or LIVE, got {environment!r}")
    if account.get("environment") and account["environment"] != environment:
        raise ValueError(
            f"action {label!r}: environment {environment} != account {account['environment']}"
        )
    ctx = f"{account['label']} · {environment}"
    # The visible spans form the accessible name, so screen readers hear the
    # account, environment and any disabled reason. aria-disabled (not
    # `disabled`) keeps the control focusable; handlers must check it.
    sep = '<span class="sr-only">, </span>'
    dis = ' aria-disabled="true"' if disabled_reason else ""
    why = f'{sep}<span class="why">{e(disabled_reason)}</span>' if disabled_reason else ""
    return (
        f'<button type="button" class="action" data-action="{e(label)}" '
        f'data-account="{e(account["id"])}" data-environment="{environment}"{dis}>'
        f'<span>{e(label)}</span>{sep}<span class="ctx">{e(ctx)}</span>{why}</button>'
    )


def bar(fraction: float, *, label: str, cls: str = "") -> str:
    width = max(0.0, min(1.0, fraction)) * 100
    return (
        f'<div class="bar {cls}" role="img" aria-label="{e(label)}">'
        f'<span style="width:{width:.1f}%"></span></div>'
    )


def field(name: str, value: str, unit: str, error: str | None) -> str:
    fid = f"f-{e(name)}"
    err = f'<span class="err" id="{fid}-err">✕ {e(error)}</span>' if error else ""
    described = f' aria-describedby="{fid}-err" aria-invalid="true"' if error else ""
    return (
        f'<div class="field"><label for="{fid}">{e(name)} ({e(unit)})</label>'
        f'<input id="{fid}" name="{e(name)}" value="{e(value)}"{described}>{err}</div>'
    )


def settings() -> str:
    return (
        '<div class="settings" role="group" aria-label="Display settings">'
        '<button type="button" data-toggle="texture" aria-pressed="true">Texture: on</button>'
        '<button type="button" data-toggle="motion" aria-pressed="true">Motion: on</button>'
        "</div>"
    )
