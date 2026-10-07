"""REST order API v1 for the demo paper accounts (ALG-3263, A10-4).

The endpoint set follows OpenAlgo's feature list — place, basket, split,
cancel, cancel-all, close-position, order book, trade book, position book,
funds — keyed by account under ``/demo/api/v1/``. Names and payloads are
ours; there is no OpenAlgo protocol, dependency or code (it is an
Indian-market bridge and a feature reference only). Execution is Nautilus:
every write runs the SAME ALG-3262 gate as the order ticket
(``tickets.gate_leg`` -> ``gate.pre_trade``) and is then enqueued for that
account's Nautilus paper worker (``engine.workers.paper``), which executes it
and journals the fill carrying its own trader / order-tag identity. Fills,
positions and funds therefore come back from the worker, never from a
parallel simulator in this process.

A worker that is not reconciled, live and heartbeat-fresh is a typed
``worker_unavailable`` error (503): nothing falls back, nothing is simulated.
PAPER only — LIVE stays hard-disabled inside the gate.

Stdlib only: the API imports this without importing Nautilus.
"""

from __future__ import annotations

import fcntl
import json
import time
from collections.abc import Callable
from decimal import Decimal
from pathlib import Path

from algobots.demo import ledger as L
from algobots.demo import tickets as T
from algobots.engine.workers import supervisor as SUP
from algobots.engine.workers.lease import Lease

WORKER_UNAVAILABLE = "worker_unavailable"
NO_OPEN_POSITION = "no_open_position"


class OrderApiError(Exception):
    """A typed v1 failure: HTTP ``status`` + machine ``code`` + human reason."""

    def __init__(self, status: int, code: str, reason: str) -> None:
        super().__init__(f"[{code}] {reason}")
        self.status, self.code, self.reason = status, code, reason


def worker_available(state_dir: str, account: str, *, now: float | None = None) -> tuple[bool, str]:
    """Is this account's worker ready to take orders? (why-not text otherwise).

    Truth sources are the worker's own heartbeat file (reconciled, fresh) and
    its durable lease (a live owner whose PID wrote that heartbeat). Anything
    else — no worker, still reconciling, stale heartbeat, dead or foreign
    lease holder — is unavailable, and the caller must refuse, not fall back.
    """
    now = time.time() if now is None else now
    hb = SUP.read_heartbeat(Path(state_dir), account)
    if not hb:
        return False, "no worker heartbeat"
    if not hb.get("reconciled"):
        return False, f"worker phase {hb.get('phase', 'starting')!r} — entry-frozen"
    beat = hb.get("last_heartbeat")
    if not beat or now - beat > SUP.HEARTBEAT_STALE_S:
        return False, "worker heartbeat stale"
    holder = Lease(Path(state_dir), account).holder()
    if holder.status != "live":
        return False, f"worker lease {holder.status}: {holder.reason}"
    if (holder.lease or {}).get("pid") != hb.get("pid"):
        return False, "heartbeat and lease name different pids"
    return True, str(hb.get("trader_id", ""))


def require_worker(state_dir: str, account: str) -> dict:
    """The worker's heartbeat, or the typed ``worker_unavailable`` refusal."""
    ok, why = worker_available(state_dir, account)
    if not ok:
        raise OrderApiError(
            503, WORKER_UNAVAILABLE, f"account {account}: {why} — no fallback exists"
        )
    return SUP.read_heartbeat(Path(state_dir), account) or {}


def inbox_path(state_dir: str, account: str) -> Path:
    return Path(state_dir) / "workers" / f"{account}.inbox.jsonl"


def enqueue(
    state_dir: str,
    parent: T.Parent,
    leg: T.Leg,
    *,
    symbol: str | None = None,
    qty: int | None = None,
) -> dict:
    """Append one execution request to the account worker's inbox (under its lock).

    ``symbol`` names the binary contract (``<event>-<YES|NO>``); entries
    without one trade the current 15m interval the worker computes itself.
    """
    req = {
        "leg_id": leg.id,
        "parent_id": parent.id,
        "account": leg.account,
        "side": leg.side,
        "kind": leg.kind,
        "notional": leg.notional,
        "qty": qty,
        "symbol": symbol,
        "path": parent.path,
        "ts": time.time(),
    }
    p = inbox_path(state_dir, leg.account)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with p.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(req) + "\n")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)
    return req


def dispatch_for(state_dir: str) -> Callable[[T.Parent, T.Leg], None]:
    """The ``tickets.submit`` dispatch hook: journal first, then hand to the worker."""
    return lambda parent, leg: enqueue(state_dir, parent, leg)


def submit(
    lg: L.Ledger,
    path: str,
    intents: list[T.Intent],
    *,
    now: float,
    state_dir: str,
    max_clip: Decimal | None = None,
    take_profit: Decimal | None = None,
    stop: Decimal | None = None,
) -> T.Parent:
    """Gate every leg (ALG-3262), then enqueue the allowed ones to their workers.

    Refuses up front with ``worker_unavailable`` for any account whose worker
    is not ready — a denied write never queues anything.
    """
    for account in sorted({i.account for i in intents}):
        require_worker(state_dir, account)
    return T.submit(
        lg,
        path,
        intents,
        now=now,
        max_clip=max_clip,
        take_profit=take_profit,
        stop=stop,
        state_dir=state_dir,
        dispatch=dispatch_for(state_dir),
    )


def cancel_all(state_dir: str, account: str, *, now: float) -> list[dict]:
    """Cancel every live (``submitted`` / ``working``) leg of one account, in place.

    Other accounts' legs on shared parents are untouched; fills are final.
    """
    out = []
    for p in T.load(state_dir):
        live = [
            x.id
            for x in p.legs
            if x.account == account and x.status in ("submitted", "working")
        ]
        if live:
            hit = T.cancel(state_dir, p.id, now=now, accounts=[account])
            out.append(
                {
                    "parent_id": p.id,
                    "path": p.path,
                    "cancelled": sum(1 for x in hit.legs if x.status == "cancelled"),
                }
            )
    return out


def close_position(
    lg: L.Ledger, state_dir: str, account: str, *, now: float, instrument: str | None = None
) -> list[T.Parent]:
    """Exit orders for the account's open worker positions (privileged at the gate).

    ``instrument`` (a worker position's ``symbol``, e.g. ``KXBTC15M-…-YES``)
    closes one position; None closes every open one, one parent each.
    """
    hb = require_worker(state_dir, account)
    positions = (hb.get("report") or {}).get("positions") or []
    wanted = [
        p
        for p in positions
        if p.get("symbol") and (instrument is None or p.get("symbol") == instrument)
    ]
    if not wanted:
        raise OrderApiError(
            404, NO_OPEN_POSITION, f"account {account} has no open worker position to close"
        )
    out = []
    for p in wanted:
        symbol = str(p["symbol"])
        qty = int(Decimal(str(p["qty"])))
        notional = (Decimal(str(p["qty"])) * L.FILL_PRICE).quantize(L.CENT)
        side = symbol.rsplit("-", 1)[-1]  # the contract being sold: YES or NO
        out.append(
            T.submit(
                lg,
                "single",
                [T.Intent(account, side, notional, "exit")],
                now=now,
                state_dir=state_dir,
                dispatch=lambda parent, leg, _symbol=symbol, _qty=qty: enqueue(
                    state_dir, parent, leg, symbol=_symbol, qty=_qty
                ),
            )
        )
    return out


def order_book(state_dir: str, account: str, status: str | None = None) -> list[dict]:
    """Every journaled leg on the account (all paths), newest first."""
    rows = T.blotter_rows(T.load(state_dir), account)
    if status is not None:
        rows = [r for r in rows if r["status"] == status]
    rows.sort(key=lambda r: r.get("leg_id", ""))  # legs of one parent stay in seq order
    rows.sort(key=lambda r: r["ts"], reverse=True)  # newest parent first (stable)
    return rows


def trade_book(state_dir: str, account: str) -> list[dict]:
    """The account's fills as executed by its worker, newest first."""
    out = []
    for r in order_book(state_dir, account, "filled"):
        out.append(
            {
                "leg_id": r["leg_id"],
                "parent_id": r["parent_id"],
                "path": r["path"],
                "kind": r["kind"],
                "side": r["side"],
                "qty": r["qty"],
                "price": r["price"],
                "notional": r["notional"],
                "fee": r["fee"],
                "ts": r["filled_ts"] or r["ts"],
                "trader_id": r["worker_trader_id"],
                "order_id": r["worker_order_id"],
                "trade_id": r["worker_trade_id"],
                "venue_account_id": r["venue_account_id"],
            }
        )
    return out


def position_book(state_dir: str, account: str) -> list[dict]:
    """Open positions as the account's worker reports them (its venue cache)."""
    hb = require_worker(state_dir, account)
    positions = (hb.get("report") or {}).get("positions")
    if positions is None:
        raise OrderApiError(
            503, WORKER_UNAVAILABLE, f"account {account}: worker reports no position book"
        )
    return list(positions)


def funds(state_dir: str, account: str) -> dict:
    """Account funds as the worker computes them (its ledger build + venue)."""
    hb = require_worker(state_dir, account)
    f = (hb.get("report") or {}).get("funds")
    if f is None:
        raise OrderApiError(
            503, WORKER_UNAVAILABLE, f"account {account}: worker reports no funds"
        )
    return dict(f)


__all__ = [
    "NO_OPEN_POSITION",
    "OrderApiError",
    "WORKER_UNAVAILABLE",
    "cancel_all",
    "close_position",
    "dispatch_for",
    "enqueue",
    "funds",
    "inbox_path",
    "order_book",
    "position_book",
    "require_worker",
    "submit",
    "trade_book",
    "worker_available",
]
