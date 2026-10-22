"""ALG-3357 demo loop: live Kalshi feed -> strategy calls -> paper fills, from the /demo API.

The observer on .243 (``kalshi-observer.service``) writes the KXBTC15M feed. The
three paper workers trade each settled interval on their Nautilus paper venues,
and the API serves the resulting ledger. This notebook only issues GET requests
against that API and refreshes on a timer. Stdlib HTTP, so the marimo image
needs no extra packages.
"""

import marimo

__generated_with = "0.25.1"
app = marimo.App(width="medium")

with app.setup:
    import json
    import os
    import time
    import urllib.request
    from datetime import UTC, datetime

    EVIDENCE_MARKER = "ALG-3357 demo loop"


@app.function
def fetch(base: str, path: str, timeout: float = 10.0) -> dict:
    with urllib.request.urlopen(f"{base.rstrip('/')}{path}", timeout=timeout) as r:
        return json.loads(r.read())


@app.function
def age(ts: float | None, now: float) -> str:
    if not ts:
        return "never"
    s = int(now - ts)
    return f"{s}s ago" if s < 120 else f"{s // 60}m ago" if s < 7200 else f"{s // 3600}h ago"


@app.function
def utc(ts: float | None) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%d %H:%M:%SZ") if ts else "—"


@app.function
def strategy_rows(state: dict) -> list[dict]:
    out = []
    for key, s in state["strategies"].items():
        d = s.get("last_decision") or {}
        out.append(
            {
                "account": key,
                "last interval": d.get("event", "—"),
                "call": d.get("status", "—"),
                "side": d.get("side") or "—",
                "stake": d.get("stake", "—"),
                "fills": s["fills"],
                "net P&L": s["net_pnl"],
                "equity": s["equity"],
                "why": d.get("reason", ""),
            }
        )
    return out


@app.function
def worker_rows(workers: dict, now: float) -> list[dict]:
    return [
        {
            "account": w["account"],
            "state": w["state"],
            "trader": w.get("trader_id"),
            "intervals seen": w.get("intervals"),
            "orders filled": w.get("orders_filled"),
            "open positions": w.get("open_positions"),
            "heartbeat": age(w.get("last_heartbeat"), now),
        }
        for w in workers["workers"]
    ]


@app.function
def history_rows(orders: dict, limit: int = 20) -> list[dict]:
    """One row per settled interval: every strategy call, plus running coin P&L.

    ``/demo/api/orders`` journals one record per account per settled interval,
    so grouping by ``ts`` reconstructs the full run history.
    """
    by_ts: dict[float, dict[str, dict]] = {}
    for o in orders.get("orders", []):
        if o.get("status") in ("filled", "abstain"):
            by_ts.setdefault(o.get("ts"), {})[o.get("account")] = o
    rows: list[dict] = []
    cum = 0.0
    for ts in sorted(by_ts):
        calls = by_ts[ts]
        row: dict = {"settled (UTC)": utc(ts)}
        for acct in ("laya", "jev", "coin"):
            o = calls.get(acct) or {}
            if o.get("status") == "filled":
                pnl = o.get("pnl")
                amt = f"{float(pnl):+.2f}" if pnl is not None else "?"
                row[acct] = "{} {}".format(o.get("side"), amt)
            else:
                row[acct] = "abstain"
        coin_pnl = (calls.get("coin") or {}).get("pnl")
        cum += float(coin_pnl) if coin_pnl is not None else 0.0
        row["coin cum P&L"] = f"{cum:+.2f}"
        rows.append(row)
    return rows[-limit:][::-1]


@app.function
def fidelity_rows(orders: dict, settlements: dict) -> dict:
    """Audit paper-fill verdicts against Kalshi's own settle marks.

    The ledger books win/loss from the feed row's outcome flag; the settlement
    row carries the exchange's actual settle value. A fill agrees when its P&L
    sign matches (side == YES) == (settle mark at/above strike).
    """
    marks = {s["event"]: s for s in settlements.get("settlements", [])}
    rows: list[dict] = []
    agree = total = 0
    for o in orders.get("orders", []):
        if o.get("status") != "filled" or o.get("source") != "strategy" or not o.get("side"):
            continue
        s = marks.get(o.get("instrument") or o.get("event"))
        if not s or o.get("pnl") is None:
            continue
        total += 1
        implied_won = (o["side"] == "YES") == (s["outcome"] == 1)
        ok = implied_won == (float(o["pnl"]) > 0)
        agree += ok
        rows.append(
            {
                "interval": s["event"],
                "fill side": o["side"],
                "strike": s["strike"],
                "settle mark": s["settle_value"],
                "kalshi says": "YES" if s["outcome"] == 1 else "NO",
                "fill P&L": f"{float(o['pnl']):+.2f}",
                "verdict": "agree" if ok else "MISMATCH",
            }
        )
    return {"agree": agree, "total": total, "rows": rows[::-1]}


@app.cell
def _():
    import marimo as mo

    return (mo,)


@app.cell
def _(mo):
    mo.md(f"""
    # Kalshi demo loop ({EVIDENCE_MARKER})

    Live KXBTC15M feed, then strategy calls, then Nautilus paper fills. Read-only GETs against
    the AlgoBots API; paper only. Fills are at the ledger's assumed 50c, and the observer
    records the real quote beside each row.
    """)
    return


@app.cell
def _(mo):
    api = mo.ui.text(
        value=os.environ.get("ALGOBOTS_API_URL", "http://algobots-api-1:8000"),
        label="AlgoBots API",
        full_width=True,
    )
    tick = mo.ui.refresh(options=["15s", "30s", "60s"], default_interval="15s")
    mo.hstack([api, tick])
    return api, tick


@app.cell
def _(api, mo, tick):
    tick  # noqa: B018 - re-run on every refresh tick
    now = time.time()
    try:
        state = fetch(api.value, "/demo/api/state")
        workers = fetch(api.value, "/demo/api/workers")
        quality = fetch(api.value, "/demo/api/quality")
        orders = fetch(api.value, "/demo/api/orders")
        settlements = fetch(api.value, "/demo/api/settlements")
        error = None
    except (OSError, ValueError) as exc:
        state = workers = quality = orders = None
        error = f"{type(exc).__name__}: {exc}"
    mo.stop(error is not None, mo.callout(mo.md(f"API unreachable: `{error}`"), kind="danger"))
    return now, orders, quality, settlements, state, workers


@app.cell
def _(mo, now, quality, state):
    pending = sum(s.get("pending", 0) for s in quality["strategies"].values())
    last = state["last_decision_ts"]
    stale = last is None or now - last > 45 * 60
    mo.vstack(
        [
            mo.md("## 1. Live feed"),
            mo.hstack(
                [
                    mo.stat(str(state["intervals"]), label="settled intervals"),
                    mo.stat(age(last, now), label="last settled decision", caption=utc(last)),
                    mo.stat(str(pending), label="pending calls (awaiting settlement)"),
                ],
                justify="start",
            ),
            mo.callout(
                mo.md(
                    "No settled interval in 45 minutes: check `kalshi-observer` on .243 "
                    "(`/opt/laya/kalshi/observer.json`) and Kalshi's exchange status."
                ),
                kind="warn",
            )
            if stale
            else mo.md(""),
        ]
    )
    return


@app.cell
def _(mo, state):
    mo.vstack(
        [
            mo.md("## 2. Strategy calls (latest settled interval)"),
            mo.ui.table(strategy_rows(state), selection=None),
        ]
    )
    return


@app.function
def blocked_gates(state: dict) -> list[dict]:
    """Strategies whose latest settled decision was blocked by the risk envelope."""
    out: list[dict] = []
    for key, s in (state.get("strategies") or {}).items():
        d = s.get("last_decision") or {}
        if d.get("status") == "BLOCKED":
            out.append(
                {
                    "strategy": key,
                    "reason": d.get("reason") or "",
                    "net_pnl": s.get("net_pnl"),
                }
            )
    return out


@app.cell
def _(mo, now, state, workers):
    gates = blocked_gates(state)
    secs_to_reset = 86400 - (now % 86400)  # daily-loss envelope resets at 00:00 UTC
    resume_in = f"{int(secs_to_reset // 3600)}h {int((secs_to_reset % 3600) // 60):02d}m"
    gate_bits = "; ".join(
        f"`{g['strategy']}` (net P&L {g['net_pnl']} USD): {g['reason']}" for g in gates
    )
    mo.vstack(
        [
            mo.md("## 3. Paper fills (one Nautilus worker per account)"),
            mo.ui.table(worker_rows(workers, now), selection=None),
            mo.callout(
                mo.md(
                    f"**Risk gate engaged** — {gate_bits}. "
                    f"The daily-loss envelope resets at **00:00 UTC** — "
                    f"fills resume automatically in **{resume_in}**, no manual reset."
                ),
                kind="warn",
            )
            if gates
            else mo.md(""),
        ]
    )
    return


@app.cell
def _(mo, orders):
    mo.vstack(
        [
            mo.md("## 4. Run history (every settled interval)"),
            mo.ui.table(history_rows(orders), selection=None),
        ]
    )
    return


@app.cell
def _(mo, orders, settlements):
    fid = fidelity_rows(orders, settlements)
    ok = fid["total"] > 0 and fid["agree"] == fid["total"]
    mo.vstack(
        [
            mo.md("## 5. Settlement fidelity (paper verdicts vs Kalshi settle marks)"),
            mo.callout(
                mo.md(
                    f"**{fid['agree']}/{fid['total']} paper fills agree with the exchange's "
                    "settlement marks** — every win/loss the ledger booked matches what "
                    "Kalshi actually settled (settle value vs strike). Any MISMATCH "
                    "here means the feed's outcome flag and the settle mark disagree."
                ),
                kind="success" if ok else "danger",
            ),
            mo.ui.table(fid["rows"], selection=None),
        ]
    )
    return


@app.function
def calibration_rows(settlements: dict) -> dict:
    """Score the book's own YES pricing against realized outcomes.

    ``mkt_mid`` is the Kalshi book's mid at decision time, read as the implied
    YES probability. Brier = mean((mid - outcome)**2): 0.25 is a coin flip,
    lower means the market carried real information about the window.
    """
    ss = sorted(
        (s for s in settlements.get("settlements", []) if s.get("outcome") in (0, 1)),
        key=lambda s: s.get("settled_ts") or 0,
    )
    rows: list[dict] = []
    briers: list[float] = []
    yes = 0
    mids = 0.0
    for s in ss:
        mid = s.get("mkt_mid")
        if mid is None:
            continue
        mid = float(mid)
        outcome = int(s["outcome"])
        briers.append((mid - outcome) ** 2)
        yes += outcome
        mids += mid
        rows.append(
            {
                "interval": s["event"],
                "book YES mid": f"{mid:.3f}",
                "kalshi says": "YES" if outcome else "NO",
                "brier": f"{(mid - outcome) ** 2:.3f}",
                "running Brier": f"{sum(briers) / len(briers):.3f}",
            }
        )
    n = len(briers)
    return {
        "n": n,
        "brier": sum(briers) / n if n else None,
        "yes_rate": yes / n if n else None,
        "mean_mid": mids / n if n else None,
        "rows": rows,
    }


@app.function
def equity_chart(orders: dict):
    """Cumulative paper P&L over settled strategy fills, oldest first."""
    import plotly.graph_objects as go

    fills = [
        o
        for o in orders.get("orders", [])
        if o.get("status") == "filled"
        and o.get("source") == "strategy"
        and o.get("pnl") is not None
    ]
    fills.sort(key=lambda o: o.get("ts") or 0)
    x: list[str] = []
    y: list[float] = []
    cum = 0.0
    for o in fills:
        cum += float(o["pnl"])
        x.append(utc(o.get("ts")))
        y.append(round(cum, 2))
    fig = go.Figure(go.Scatter(x=x, y=y, mode="lines+markers", name="cum P&L"))
    fig.update_layout(
        height=280,
        margin=dict(l=8, r=8, t=36, b=8),
        xaxis_title="fill settled (UTC)",
        yaxis_title="cumulative P&L (USD)",
        showlegend=False,
    )
    return fig, len(fills)


@app.cell
def _(mo, orders, settlements):
    cal = calibration_rows(settlements)
    fig, n_fills = equity_chart(orders)
    brier = f"{cal['brier']:.3f}" if cal["brier"] is not None else "-"
    yes_rate = f"{cal['yes_rate']:.0%}" if cal["yes_rate"] is not None else "-"
    mean_mid = f"{cal['mean_mid']:.3f}" if cal["mean_mid"] is not None else "-"
    mo.vstack(
        [
            mo.md("## 6. Book calibration & paper equity"),
            mo.callout(
                mo.md(
                    f"Over **{cal['n']}** settled intervals the Kalshi book priced YES "
                    f"at **{mean_mid}** mid on average; YES actually hit **{yes_rate}**. "
                    f"Running **Brier {brier}** (0.25 = coin flip - lower means the "
                    "book's price carried real information about the next 15 minutes)."
                ),
                kind="info",
            ),
            mo.ui.plotly(fig) if n_fills else mo.md("_No settled fills yet._"),
            mo.ui.table(cal["rows"][-15:], selection=None),
        ]
    )
    return


if __name__ == "__main__":
    app.run()
