"""Control-plane bridge endpoints (ALG-3340): intent in, fills/positions out.

The NoFX side talks to exactly these:

- ``POST /bridge/intents`` — admit an order intent (scope -> PAPER-only ->
  worker available -> the ALG-3262 gate) and write it to the shared channel.
  A refused intent is never written.
- ``GET  /bridge/fills?account=`` — the account's Nautilus ``OrderFilled``
  records from ``bridge/fills/`` JSONL, as mirrored by ITS paper worker.
- ``GET  /bridge/positions/{account}`` — open positions as the account's
  worker computes them (its venue cache; no parallel simulator).
- ``GET  /bridge/intents/{intent_id}`` — where an intent is (admitted /
  processing / done) and its terminal outcome.
- ``GET  /bridge/stats`` — traffic + latency on the bridge endpoints and
  on-disk channel counters (OpenAlgo pull #6, pattern only).

There is no order route here: execution lives in the workers' Nautilus
engines (ADR 0001). Stdlib + demo imports only — no Nautilus in this process.
"""

from __future__ import annotations

import time
from dataclasses import asdict
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from algobots.api.config import get_settings
from algobots.bridge import stats as ST
from algobots.bridge.admission import BridgeApiError, admit
from algobots.bridge.channel import (
    channel_stats,
    find_intent,
    read_fills,
    write_intent,
)
from algobots.demo import orderapi as V
from algobots.demo.router import _ledger  # the app's one cached ledger build
from algobots.demo.scope import Scope, current_scope, narrow, resolve

router = APIRouter(tags=["bridge"])


class IntentIn(BaseModel):
    """The wire shape from NoFX: what to trade, on which paper account."""

    account: str
    side: str  # buy | sell
    qty: int  # whole contracts
    symbol: str | None = None  # <event>-<YES|NO>; default: current interval YES
    ts_utc: str | None = None  # ISO-8601; default: server now
    mode: str = "PAPER"  # LIVE is refused: no live venue approved


def _bridge_dir() -> Path:
    d = (get_settings().bridge_dir or "").strip()
    if not d:
        raise HTTPException(
            503,
            {
                "code": "bridge_disabled",
                "reason": "ALGOBOTS_BRIDGE_DIR is not configured on the control plane",
            },
        )
    return Path(d)


def _typed(exc: BridgeApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"error": {"code": exc.code, "reason": exc.reason}}
    )


@router.post("/bridge/intents")
def post_intent(o: IntentIn, scope: Scope = Depends(current_scope)) -> JSONResponse:
    """Admit one order intent onto the channel for the account's paper worker."""
    t0 = time.perf_counter()
    try:
        bridge = _bridge_dir()
        s = get_settings()
        lg, _ = _ledger()
        intent = admit(
            o.model_dump(),
            scope=scope,
            ledger=narrow(lg, scope),
            state_dir=s.demo_state_dir,
        )
        write_intent(bridge, asdict(intent))
        return JSONResponse(
            status_code=201,
            content={
                "intent_id": intent.intent_id,
                "status": intent.status,
                "account": intent.account,
                "venue": intent.venue,
                "symbol": intent.symbol,
                "side": intent.side,
                "qty": intent.qty,
                "notional": intent.notional,
                "kind": intent.kind,
                "ts_utc": intent.ts_utc,
                "admitted_ts": intent.admitted_ts,
            },
        )
    except BridgeApiError as exc:
        return _typed(exc)
    finally:
        ST.observe("POST /bridge/intents", t0)


@router.get("/bridge/fills")
def get_fills(
    account: str,
    limit: int = Query(default=50, ge=1, le=500),
    scope: Scope = Depends(current_scope),
) -> dict:
    """The account's fill records (Nautilus OrderFilled, mirrored by its worker)."""
    t0 = time.perf_counter()
    try:
        key = resolve(account, scope)
        return {
            "account": key,
            "fills": read_fills(_bridge_dir(), key, limit),
        }
    finally:
        ST.observe("GET /bridge/fills", t0)


@router.get("/bridge/positions/{account}")
def get_position(account: str, scope: Scope = Depends(current_scope)) -> dict:
    """Open positions exactly as the account's paper worker reports them."""
    t0 = time.perf_counter()
    try:
        key = resolve(account, scope)
        try:
            hb = V.require_worker(get_settings().demo_state_dir, key)
        except V.OrderApiError as exc:
            return JSONResponse(
                status_code=exc.status,
                content={"error": {"code": exc.code, "reason": exc.reason}},
            )
        positions = (hb.get("report") or {}).get("positions")
        if positions is None:
            raise HTTPException(
                503,
                {
                    "code": V.WORKER_UNAVAILABLE,
                    "reason": f"account {key}: worker reports no position book",
                },
            )
        return {"account": key, "trader_id": hb.get("trader_id"), "positions": positions}
    finally:
        ST.observe("GET /bridge/positions", t0)


@router.get("/bridge/intents/{intent_id}")
def get_intent(intent_id: str, scope: Scope = Depends(current_scope)) -> dict:
    """Where an intent is: admitted -> processing -> done (filled / rejected)."""
    t0 = time.perf_counter()
    try:
        found = find_intent(_bridge_dir(), intent_id)
        if found is None:
            raise HTTPException(404, {"code": "unknown_intent", "reason": f"no intent {intent_id}"})
        state, payload = found
        owner = str(payload.get("account", "")).strip().lower()
        if owner:
            resolve(owner, scope)  # an intent is visible only to its account's grantees
        return {"intent_id": intent_id, "state": state, "intent": payload}
    finally:
        ST.observe("GET /bridge/intents", t0)


@router.get("/bridge/stats")
def get_stats() -> dict:
    """Endpoint traffic + latency (p50/p95/max) and on-disk channel counters."""
    t0 = time.perf_counter()
    try:
        out: dict = {"bridge_dir_configured": bool((get_settings().bridge_dir or "").strip())}
        out.update(ST.snapshot())
        if out["bridge_dir_configured"]:
            out["channel"] = channel_stats(_bridge_dir())
        return out
    finally:
        ST.observe("GET /bridge/stats", t0)


__all__ = ["IntentIn", "router"]
