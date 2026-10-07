"""The one pre-trade check for /demo — every order path calls ``pre_trade``.

Strategy decisions (``ledger.build``), ticket singles, basket legs, split
children, bracket children and broadcast legs all go through this function,
so a rule added here applies everywhere. It is built on ``algobots.risk``:
the ``RiskGate`` owns the daily-loss envelope, the rate breakers, the
order-value clamp and the audit row for each firing; this module adds the demo
rails around it (account mode, kill switch, sleeve floor, affordability).

Order of checks (first denial wins):

1. account mode: LIVE is hard-disabled ("no live venue approved")
2. kill switch: blocks entries; exits stay privileged
3. sleeve floor: equity below min stake + fee blocks entries (unless the
   daily-loss envelope already tripped, which ``RiskGate`` reports first)
4. ``RiskGate.approve_order``: daily loss → breakers → order-value clamp
5. affordability: an entry never stakes more than the sleeve can pay

Callers must reach this through the module (``gate.pre_trade``) so a test spy
patched onto the module sees every path.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal

from algobots.risk import InMemorySink, RiskEnvelope, RiskGate, RiskLimits

MODES = ("PAPER", "LIVE")
LIVE_DISABLED = "no live venue approved"
PATHS = ("strategy", "single", "broadcast", "basket", "split", "bracket")


@dataclass(frozen=True)
class GateRequest:
    account: str
    path: str  # one of PATHS
    value: Decimal  # requested notional, USD
    equity: Decimal  # sleeve equity before this order
    floor: Decimal  # min stake + fee
    daily_pnl: Decimal
    kill_engaged: bool
    kind: str = "entry"  # entry / exit (bracket take-profit + stop are exits)
    mode: str = "PAPER"
    now: float | None = None
    ticker: str | None = None
    fee: object = None  # callable(stake) -> fee; enables the affordability cap


@dataclass(frozen=True)
class GateResult:
    allowed: bool
    approved: Decimal  # notional allowed through (0 when denied)
    clamped: bool = False
    code: str | None = None  # machine reason for a denial
    reason: str = ""  # human reason: denial cause, or clamp note


def risk_gate(envelope: RiskEnvelope, sink=None) -> RiskGate:  # noqa: ANN001
    # The demo trades single binary contracts, not weights: the weight limits are
    # carried for completeness (RiskGate requires them) and never bind here.
    return RiskGate(
        limits=RiskLimits(max_position_pct=1.0, max_gross_exposure=1.0),
        envelope=envelope,
        sink=sink if sink is not None else InMemorySink(),
    )


def dry_run(risk: RiskGate) -> RiskGate:
    """A throwaway copy for previews: same breaker state, nothing recorded or audited."""
    g = RiskGate(limits=risk.limits, envelope=risk.envelope, sink=InMemorySink())
    g.breakers = copy.deepcopy(risk.breakers)
    return g


def _deny(code: str, reason: str) -> GateResult:
    return GateResult(allowed=False, approved=Decimal(0), code=code, reason=reason)


def pre_trade(req: GateRequest, risk: RiskGate) -> GateResult:
    if req.mode not in MODES:
        return _deny("mode", f"unknown account mode {req.mode!r}")
    if req.mode == "LIVE":
        return _deny("live_disabled", f"LIVE disabled — {LIVE_DISABLED}")
    env = risk.envelope
    if req.kind == "entry":
        if req.kill_engaged:
            return _deny("kill_switch", "kill switch engaged — entry blocked")
        if not env.check_daily_loss(req.daily_pnl).tripped and req.equity < req.floor:
            return _deny(
                "sleeve_floor", f"sleeve equity {req.equity} USD below minimum stake + fee"
            )
    d = risk.approve_order(
        kind=req.kind,  # type: ignore[arg-type]
        value=req.value,
        daily_pnl=req.daily_pnl,
        deployment_id=req.account,
        ticker=req.ticker,
        now=req.now,
    )
    if not d.allowed:
        if d.reason == "max_daily_loss":
            return _deny(
                "max_daily_loss", f"daily-loss envelope (−{env.max_daily_loss} USD) exhausted"
            )
        return _deny(d.reason or "breaker", f"rate breaker: {d.reason}")
    approved = d.approved_value if d.approved_value is not None else req.value
    clamped = approved != req.value
    if req.kind == "entry" and req.fee is not None:
        # stake + fee never exceeds what the sleeve holds
        approved = min(approved, (req.equity - req.fee(req.equity)).quantize(Decimal("0.01")))
    note = f"size clamped {req.value} → {approved} USD (max order value)" if clamped else ""
    return GateResult(allowed=True, approved=approved, clamped=clamped, reason=note)
