"""Routes for the live paper-trading demo: page, JSON state, kill switch."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from algobots.api.config import get_settings
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo.page import render

router = APIRouter(tags=["demo"])


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


@router.get("/demo", response_class=HTMLResponse)
def demo_page() -> str:
    lg, start = _ledger()
    return render(lg, start=start)


@router.get("/demo/api/state")
def demo_state() -> dict:
    lg, start = _ledger()
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


@router.post("/demo/kill-switch", include_in_schema=False)
async def kill_switch(request: Request) -> RedirectResponse:
    form = parse_qs((await request.body()).decode())
    engaged = form.get("engaged", ["on"])[0] == "on"
    host = request.client.host if request.client else "unknown"
    name = form.get("actor", [""])[0].strip()[:40]
    actor = f"{name} via dashboard ({host})" if name else f"dashboard ({host})"
    killswitch.set_engaged(get_settings().demo_state_dir, engaged, actor=actor)
    return RedirectResponse("/demo", status_code=303)
