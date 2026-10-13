"""Execution admission for bridge order intents (ALG-3340).

The control plane never executes anything; it decides whether an intent may
reach a worker, then writes it to the channel. Admission is the SAME
discipline as every other demo order path (ALG-3262): scope (account
grants) -> PAPER-only -> worker available (reconciled, heartbeat-fresh,
lease-live) -> ``gate.pre_trade`` (kill switch, sleeve floor, daily-loss
envelope, order-value clamp, affordability). No check of these may be
skipped, and nothing is queued when any of them refuses.

Stdlib only: the API process imports this without importing Nautilus.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from algobots.bridge.channel import now_id, valid_symbol
from algobots.demo import blotter as B
from algobots.demo import ledger as L
from algobots.demo import orderapi as V
from algobots.demo import tickets as T
from algobots.demo.scope import Scope, resolve

SIDES = ("buy", "sell")
MAX_QTY = 10_000  # the paper quote's displayed size; the gate clamps harder


class BridgeApiError(Exception):
    """A typed bridge failure: HTTP ``status`` + machine ``code`` + reason."""

    def __init__(self, status: int, code: str, reason: str) -> None:
        super().__init__(f"[{code}] {reason}")
        self.status, self.code, self.reason = status, code, reason


@dataclass(frozen=True)
class AdmittedIntent:
    """The normalized intent record written to ``bridge/intents/``."""

    intent_id: str
    account: str
    symbol: str  # <event>-<YES|NO>, the contract to trade
    side: str  # buy | sell
    qty: int  # whole contracts
    notional: str  # qty * fill price, USD
    kind: str  # entry (buy) | exit (sell)
    ts_utc: str  # caller-asserted intent time, ISO-8601 Z
    admitted_ts: float  # server clock when admitted
    status: str = "admitted"
    mode: str = "PAPER"
    venue: str = ""  # PAPER_<ACCT>, stamped at admission
    source: str = "bridge"


def current_event(now: float) -> str:
    """The KXBTC15M interval id an entry at ``now`` trades (worker's twin).

    Duplicated from ``engine.workers.paper`` (stdlib-only here): the default
    symbol when a caller does not name a contract.
    """
    slot = datetime.fromtimestamp(int(now // 900) * 900, UTC)
    return f"{B.INSTRUMENT}-{slot.strftime('%y%b%d%H%M').upper()}"


def _parse_ts(raw: str) -> str:
    try:
        ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        raise BridgeApiError(422, "invalid_ts_utc", f"ts_utc {raw!r} is not ISO-8601") from None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)  # naive means UTC, asserted
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _qty(raw) -> int:
    try:
        qty = int(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        raise BridgeApiError(422, "invalid_qty", f"qty {raw!r} is not a whole number") from None
    if not 1 <= qty <= MAX_QTY:
        raise BridgeApiError(422, "invalid_qty", f"qty must be 1..{MAX_QTY} contracts")
    return qty


def _symbol(raw: str | None, now: float) -> str:
    if raw is None or not str(raw).strip():
        return f"{current_event(now)}-YES"  # the current 15m interval, YES contract
    symbol = str(raw).strip()
    if not valid_symbol(symbol):
        raise BridgeApiError(422, "invalid_symbol", f"symbol {symbol!r} is not <event>-<YES|NO>")
    event, _, outcome = symbol.rpartition("-")
    return f"{event}-{outcome.upper()}"


def admit(
    raw: dict,
    *,
    scope: Scope,
    ledger: L.Ledger,
    state_dir: str,
    now: float | None = None,
) -> AdmittedIntent:
    """Validate + admit one intent through the full pre-trade discipline.

    Raises :class:`BridgeApiError` on the first refusal; a refused intent is
    never written to the channel.
    """
    now = time.time() if now is None else now
    account = resolve(str(raw.get("account", "")).strip().lower(), scope)  # 404/403

    side = str(raw.get("side", "")).strip().lower()
    if side not in SIDES:
        raise BridgeApiError(422, "invalid_side", f"side must be one of {SIDES}")

    mode = str(raw.get("mode", "PAPER")).strip().upper()
    if mode != "PAPER":
        raise BridgeApiError(403, "live_disabled", "LIVE disabled — no live venue approved")

    qty = _qty(raw.get("qty"))
    symbol = _symbol(raw.get("symbol"), now)
    ts_utc = _parse_ts(raw.get("ts_utc") or datetime.fromtimestamp(now, UTC).isoformat())

    try:
        V.require_worker(state_dir, account)  # typed 503: no fallback exists
    except V.OrderApiError as exc:
        raise BridgeApiError(exc.status, exc.code, exc.reason) from None

    kind = "entry" if side == "buy" else "exit"
    book = ledger.books[account]
    gate = T.make_gate(T.load(state_dir), state_dir)
    from algobots.demo import gate as G  # late: keeps the module import graph flat

    decision = G.pre_trade(
        G.GateRequest(
            account=account,
            path="bridge",
            value=(qty * L.FILL_PRICE).quantize(L.CENT),
            equity=book.equity,
            floor=L.MIN_STAKE + L.fee_for(L.MIN_STAKE),
            daily_pnl=B.day_pnl(book, B.today(now)),
            kill_engaged=bool(ledger.kill.get("engaged")),
            kind=kind,
            now=now,
            ticker=B.INSTRUMENT,
            fee=L.fee_for if kind == "entry" else None,
        ),
        gate,
    )
    if not decision.allowed:
        raise BridgeApiError(403, decision.code or "gate_denied", decision.reason)
    approved_qty = int(decision.approved / L.FILL_PRICE)
    if approved_qty < 1:
        raise BridgeApiError(
            403, "clamped_to_zero", f"order value clamped to {decision.approved} USD — no contract"
        )

    return AdmittedIntent(
        intent_id=now_id(now),
        account=account,
        symbol=symbol,
        side=side,
        qty=approved_qty,
        notional=str((approved_qty * L.FILL_PRICE).quantize(L.CENT)),
        kind=kind,
        ts_utc=ts_utc,
        admitted_ts=now,
        venue=f"PAPER_{account.upper()}",
    )


__all__ = [
    "AdmittedIntent",
    "BridgeApiError",
    "SIDES",
    "admit",
    "current_event",
]
