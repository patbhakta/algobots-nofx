"""Routes for the live paper-trading demo: terminal page, JSON views, kill switch."""

from __future__ import annotations

import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from algobots.api.config import get_settings
from algobots.demo import blotter as B
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo.page import render, render_denied
from algobots.demo.scope import Denied, Scope, current_scope, narrow, resolve
from algobots.engine.workers.supervisor import Supervisor, WorkerStatus

router = APIRouter(tags=["demo"])
SUPERVISOR: Supervisor | None = None


def start_workers() -> None:
    """Spawn one paper worker per demo account when enabled (API lifespan)."""
    global SUPERVISOR
    s = get_settings()
    if not s.demo_workers_enabled or SUPERVISOR is not None:
        return
    SUPERVISOR = Supervisor(list(L.STRATEGIES), Path(s.demo_state_dir), poll=s.demo_worker_poll_s)
    SUPERVISOR.start()


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
    )
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


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
