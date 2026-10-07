"""Routes for the live paper-trading demo: terminal page, JSON views, kill switch."""

from __future__ import annotations

import time
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from algobots.api.config import get_settings
from algobots.demo import blotter as B
from algobots.demo import decisions as D
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo import studio as S
from algobots.demo.page import render, render_denied
from algobots.demo.scope import Denied, Scope, current_scope, narrow, resolve
from algobots.demo.studio_page import render_studio
from algobots.engine.workers.supervisor import LeaseDenied, Supervisor, WorkerStatus

router = APIRouter(tags=["demo"])
SUPERVISOR: Supervisor | None = None


def start_workers() -> None:
    """Spawn one paper worker per demo account when enabled (API lifespan)."""
    global SUPERVISOR
    s = get_settings()
    if not s.demo_workers_enabled or SUPERVISOR is not None:
        return
    SUPERVISOR = Supervisor(list(L.STRATEGIES), Path(s.demo_state_dir), poll=s.demo_worker_poll_s)
    try:
        SUPERVISOR.start()
    except LeaseDenied:
        pass  # the API still boots; denied accounts show state "denied" with the reason


def stop_workers() -> None:
    global SUPERVISOR
    if SUPERVISOR is not None:
        SUPERVISOR.stop()
        SUPERVISOR = None


def _ledger() -> tuple[L.Ledger, str]:
    s = get_settings()
    start = datetime.strptime(s.demo_start, "%Y-%m-%d").replace(tzinfo=UTC)
    rows = L.load_rows(Path(s.demo_feed_path), since_ts=start.timestamp())
    refills = [
        datetime.strptime(t.strip(), "%Y-%m-%dT%H:%M").replace(tzinfo=UTC).timestamp()
        for t in s.demo_sleeve_refills.split(",")
        if t.strip()
    ]
    return L.build(rows, killswitch.read(s.demo_state_dir), refills), s.demo_start


@router.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/demo", status_code=307)


def _scoped(scope: Scope) -> tuple[L.Ledger, str]:
    lg, start = _ledger()
    return narrow(lg, scope), start


def _supervisor_down(workers: list[dict]) -> bool:
    """Workers were asked for but the supervisor is gone or a worker died."""
    if not get_settings().demo_workers_enabled:
        return False
    return SUPERVISOR is None or any(w["state"] in ("exited", "stopped") for w in workers)


@router.get("/demo", response_class=HTMLResponse)
def demo_page(
    account: str | None = None, status: str | None = None, scope: Scope = Depends(current_scope)
) -> HTMLResponse:
    try:
        key = resolve(account, scope)
    except Denied as d:
        return HTMLResponse(render_denied(d.status_code, d.account, d.why), d.status_code)
    lg, start = _scoped(scope)
    workers = [w for w in _workers() if w["account"] in scope.accounts]
    html = render(
        lg,
        start=start,
        account=key,
        status=status,
        workers={w["account"]: w for w in workers},
        supervisor_down=_supervisor_down(workers),
        studio=S.load(get_settings().demo_state_dir),
        quality=_quality(scope),
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


def _quality(scope: Scope) -> D.Quality:
    """Log every decision (unscoped, server-side); score only the granted accounts."""
    lg, _ = _ledger()
    return D.sync(Path(get_settings().demo_state_dir), lg, accounts=scope.accounts)


@router.get("/demo/api/decisions")
def demo_decisions(account: str | None = None, scope: Scope = Depends(current_scope)) -> dict:
    """Decision-quality scorecard + reflection; the log itself stays append-only on disk."""
    key = resolve(account, scope)
    q = _quality(scope)
    return {
        "account": key,
        "logged": q.logged,
        "settled": len(q.settled),
        "min_n": D.MIN_N,
        "scores": {k: asdict(s) for k, s in q.scores.items() if key in (B.ALL, k)},
        "losses": [
            {**x.rec, "outcome": x.outcome, "lesson": q.lessons.get(x.rec["decision_id"])}
            for x in D.losses(q.settled, None if key == B.ALL else key)
        ],
    }


@router.get("/demo/api/positions")
def demo_positions(account: str | None = None, scope: Scope = Depends(current_scope)) -> dict:
    key = resolve(account, scope)
    lg, _ = _scoped(scope)
    now = time.time()
    return {"account": key, "as_of": now, "positions": B.positions(lg, now, key)}


@router.get("/demo/api/orders")
def demo_orders(
    account: str | None = None,
    status: str | None = None,
    limit: int = Query(200, ge=1, le=5000),
    scope: Scope = Depends(current_scope),
) -> dict:
    key = resolve(account, scope)
    lg, _ = _scoped(scope)
    st = B.status_key(status)
    return {"account": key, "status": st, "orders": B.orders(lg, key, st, limit)}


@router.get("/demo/api/state")
def demo_state(scope: Scope = Depends(current_scope)) -> dict:
    resolve(None, scope)
    lg, start = _scoped(scope)
    return {
        "paper_since": start,
        "last_decision_ts": lg.last_ts,
        "intervals": len(lg.rows),
        "kill_switch": {k: v for k, v in lg.kill.items() if k != "history"},
        "clamp_events": len(lg.clamp_events),
        "sleeve_refills": lg.refill_ts,
        "strategies": {
            k: {
                "name": b.name,
                "equity": str(b.equity),
                "allocated": str(b.allocated),
                "exhausted": b.exhausted,
                "net_pnl": str(b.pnl),
                "fees": str(b.fees),
                "fills": len(b.fills),
                "hit_rate": L.hit_rate(b),
                "max_drawdown": str(b.max_drawdown),
                "last_decision": (
                    {
                        "event": b.decisions[-1].event,
                        "status": b.decisions[-1].status,
                        "side": b.decisions[-1].side,
                        "stake": str(b.decisions[-1].stake),
                        "reason": b.decisions[-1].reason,
                    }
                    if b.decisions
                    else None
                ),
            }
            for k, b in lg.books.items()
        },
    }


def _workers() -> list[dict]:
    sup = SUPERVISOR
    if sup is None:
        return [asdict(WorkerStatus(account=a, state="not_started")) for a in L.STRATEGIES]
    return sup.snapshot()


@router.get("/demo/api/workers")
def demo_workers(account: str | None = None, scope: Scope = Depends(current_scope)) -> dict:
    key = resolve(account, scope)
    show = scope.accounts if key == B.ALL else (key,)
    workers = [w for w in _workers() if w["account"] in show]
    return {
        "account": key,
        "enabled": SUPERVISOR is not None,
        "ready": all(w["state"] == "ready" for w in workers),
        "supervisor_down": _supervisor_down(workers),
        "workers": workers,
    }


@router.post("/demo/kill-switch", include_in_schema=False)
async def kill_switch(request: Request, scope: Scope = Depends(current_scope)) -> RedirectResponse:
    form = parse_qs((await request.body()).decode())
    key = resolve(form.get("account", [None])[0], scope)
    if len(scope.accounts) != len(L.STRATEGIES):  # it halts every account: needs every grant
        raise Denied(403, B.ALL, "kill switch spans all accounts")
    engaged = form.get("engaged", ["on"])[0] == "on"
    host = request.client.host if request.client else "unknown"
    name = form.get("actor", [""])[0].strip()[:40]
    actor = f"{name} via dashboard ({host})" if name else f"dashboard ({host})"
    killswitch.set_engaged(get_settings().demo_state_dir, engaged, actor=actor)
    return RedirectResponse("/demo" if key == B.ALL else f"/demo?account={key}", status_code=303)


# --- strategy studio (ALG-3256) ----------------------------------------------------


def _dec(raw: str | None) -> Decimal | None:
    try:
        return Decimal(raw.strip()) if raw and raw.strip() else None
    except InvalidOperation:
        raise S.StudioError(f"'{raw}' is not a number") from None


def _sizing(q: dict) -> dict:
    mode = q.get("mode") or "equal"
    return {
        "mode": mode,
        "amount": _dec(q.get("amount")) if mode == "equal" else None,
        "pct": _dec(q.get("pct")) if mode == "pct" else None,
    }


def _studio_query(request: Request) -> dict:
    qp = request.query_params
    return {
        "version": qp.get("version"),
        "accounts": qp.getlist("accounts"),
        "mode": qp.get("mode"),
        "amount": qp.get("amount"),
        "pct": qp.get("pct"),
    }


@router.get("/demo/studio", response_class=HTMLResponse)
def studio_page(request: Request, scope: Scope = Depends(current_scope)) -> HTMLResponse:
    resolve(None, scope)  # no grants -> 403
    lg, start = _scoped(scope)
    vis = S.visible(scope.accounts)
    st = S.load(get_settings().demo_state_dir)
    q, pv, error = _studio_query(request), None, None
    v = st.by_hash(q["version"] or "")
    if v and q["accounts"]:
        try:
            pv = S.preview(
                st,
                v,
                q["accounts"],
                kill_engaged=bool(lg.kill.get("engaged")),
                visible=vis,
                **_sizing(q),
            )
        except S.StudioError as exc:
            error = str(exc)
    flash = request.query_params.get("flash")
    html = render_studio(st, lg, start=start, q=q, pv=pv, error=error, flash=flash, visible=vis)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@router.get("/demo/api/strategies")
def demo_strategies(scope: Scope = Depends(current_scope)) -> dict:
    resolve(None, scope)
    vis = S.visible(scope.accounts)
    st = S.load(get_settings().demo_state_dir)
    return {
        "versions": [
            {**asdict(v), "name": S.DEFINITIONS[v.definition].name, **_defn(v.definition)}
            for v in st.versions
            if S.DEFINITIONS[v.definition].kind != "live" or v.definition in vis
        ],
        "deployments": [asdict(d) for d in st.deployments if d.account in vis],
    }


def _defn(key: str) -> dict:
    d = S.DEFINITIONS[key]
    return {"kind": d.kind, "venue": d.venue, "label": d.label}


@router.get("/demo/api/studio/preview")
def demo_preview(request: Request, scope: Scope = Depends(current_scope)) -> dict:
    resolve(None, scope)
    lg, _ = _scoped(scope)
    st = S.load(get_settings().demo_state_dir)
    q = _studio_query(request)
    v = st.by_hash(q["version"] or "")
    if v is None:
        raise HTTPException(404, f"unknown strategy version '{q['version']}'")
    try:
        pv = S.preview(
            st,
            v,
            q["accounts"],
            kill_engaged=bool(lg.kill.get("engaged")),
            visible=S.visible(scope.accounts),
            **_sizing(q),
        )
    except S.StudioError as exc:
        raise HTTPException(422, str(exc)) from None
    return {
        "version": v.hash,
        "mode": pv.mode,
        "requested": str(pv.requested),
        "allocated": str(pv.allocated),
        "undeployed": str(pv.undeployed),
        "lines": [
            {k: str(x) if isinstance(x, Decimal) else x for k, x in asdict(ln).items()}
            for ln in pv.lines
        ],
    }


def _actor(request: Request, form: dict) -> str:
    host = request.client.host if request.client else "unknown"
    name = form.get("actor", [""])[0].strip()[:40]
    return f"{name} via studio ({host})" if name else f"studio ({host})"


@router.post("/demo/studio/deploy", include_in_schema=False)
async def studio_deploy(
    request: Request, scope: Scope = Depends(current_scope)
) -> RedirectResponse:
    resolve(None, scope)
    form = parse_qs((await request.body()).decode())
    q = {
        "version": form.get("version", [""])[0],
        "accounts": form.get("accounts", []),
        "mode": form.get("mode", ["equal"])[0],
        "amount": form.get("amount", [""])[0],
        "pct": form.get("pct", [""])[0],
    }
    s = get_settings()
    try:
        _, made = S.deploy(
            s.demo_state_dir,
            q["version"],
            q["accounts"],
            kill_engaged=bool(killswitch.read(s.demo_state_dir).get("engaged")),
            visible=S.visible(scope.accounts),
            actor=_actor(request, form),
            **_sizing(q),
        )
        flash = f"Created {len(made)} paper deployment(s): " + ", ".join(d.id for d in made)
    except S.StudioError as exc:
        flash = f"Deploy refused: {exc}"
    return RedirectResponse(f"/demo/studio?{urlencode({'flash': flash})}", status_code=303)


@router.post("/demo/studio/edit", include_in_schema=False)
async def studio_edit(request: Request, scope: Scope = Depends(current_scope)) -> RedirectResponse:
    resolve(None, scope)
    form = parse_qs((await request.body()).decode())
    key = form.get("definition", [""])[0]
    params: dict = {}
    for k, vals in form.items():
        if not k.startswith("p_"):
            continue
        val = vals[0].strip()
        if k == "p_weights":
            try:
                params["weights"] = {
                    sym.strip(): float(w) for sym, w in (p.split("=") for p in val.split(",") if p)
                }
            except ValueError:
                params["weights"] = val  # let typed validation report it
        else:
            params[k[2:]] = val
    try:
        v = S.edit(get_settings().demo_state_dir, key, params, actor=_actor(request, form))
        flash = f"Saved {S.DEFINITIONS[key].name} v{v.version} · artifact {v.short}"
        q = {"version": v.short, "flash": flash}
    except S.StudioError as exc:
        q = {"flash": f"Edit refused: {exc}"}
    return RedirectResponse(f"/demo/studio?{urlencode(q)}", status_code=303)
