"""Order ticket: one paper order type, four paths, one risk gate (Fincept R1).

Paths (study ``alg-3070-fincept-terminal-feasibility.md`` §3 R1):

- ``single``    — one account.
- ``broadcast`` — one order fanned to N accounts, one result per account
                  (Fincept ``broadcast_order``).
- ``basket``    — several orders submitted as one unit.
- ``split``     — one order chunked under a max clip
                  (Fincept ``place_order_auto_split``).

Every path builds a parent of legs and every leg goes through :func:`gate_leg`,
the single risk gate: demo kill switch -> sleeve floor -> ``risk.RiskGate``
(daily-loss envelope, rate breakers, order-value clamp). Exits are privileged:
nothing blocks or shrinks an exit. A denied leg records the stated reason.

Fills are paper only: the assumed 50c mid plus the Kalshi taker fee, exactly
as ``demo.ledger``. Ticket fills are journaled to ``ticket-orders.jsonl``; they
do not feed back into the strategy books, which stay a replay of the feed.
Rate-breaker state is rebuilt from that journal on every submit, so the gate
is deterministic and survives restarts.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path

from algobots.api.approvals.service import classify_broadcast
from algobots.demo import blotter as B
from algobots.demo import ledger as L
from algobots.risk import JsonlSink, RateBreakers, RiskGate, RiskLimits

PATHS = ("single", "broadcast", "basket", "split")
SIDES = ("YES", "NO")
KINDS = ("entry", "exit")
INTERVAL_S = 15 * 60
BRACKET_UNSUPPORTED = (
    "bracket unsupported for KXBTC15M binary 15m contracts — the contract settles at "
    "the interval close, so there is no stop/target to work"
)
PAPER_NOTE = (
    f"paper only · fills at the assumed {L.FILL_PRICE} mid + Kalshi taker fee "
    "(no order book captured)"
)
# weight limits are portfolio-construction rails; the ticket gates notional only
LIMITS = RiskLimits(max_position_pct=1.0, max_gross_exposure=1.0)


class TicketError(ValueError):
    """Malformed ticket (unknown path/account/side, bad size) — 422 at the API."""


@dataclass(frozen=True)
class Intent:
    account: str
    side: str
    notional: Decimal
    kind: str = "entry"

    def __post_init__(self) -> None:
        if self.account not in L.STRATEGIES:
            raise TicketError(f"unknown account {self.account!r}")
        if self.side not in SIDES:
            raise TicketError(f"side must be one of {SIDES}")
        if self.kind not in KINDS:
            raise TicketError(f"kind must be one of {KINDS}")
        if self.notional <= 0:
            raise TicketError("notional must be > 0 USD")


@dataclass
class Leg:
    id: str
    parent_id: str
    seq: int
    account: str
    side: str
    kind: str
    requested: str
    status: str  # filled / blocked
    reason: str
    notional: str = "0"
    qty: int = 0
    price: str | None = None
    fee: str = "0"
    clamped: bool = False


@dataclass
class Parent:
    id: str
    path: str
    ts: float
    instrument: str
    expiry_ts: float
    state: str  # classify_broadcast state, or "rejected" when no leg was sent
    legs: list[Leg] = field(default_factory=list)
    note: str = PAPER_NOTE


def _path(state_dir: str) -> Path:
    return Path(state_dir) / "ticket-orders.jsonl"


def load(state_dir: str) -> list[Parent]:
    p = _path(state_dir)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            d = json.loads(line)
            d["legs"] = [Leg(**x) for x in d["legs"]]
            out.append(Parent(**d))
        except (ValueError, TypeError, KeyError):
            continue
    return out


def _append(state_dir: str, parent: Parent) -> None:
    p = _path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(parent)) + "\n")


def make_gate(history: Iterable[Parent], state_dir: str | None = None) -> RiskGate:
    """A RiskGate whose breakers have replayed every journaled filled leg."""
    breakers = RateBreakers(clock=lambda: 0.0)
    for parent in history:
        for leg in parent.legs:
            if leg.status == "filled":
                breakers.record(leg.kind, deployment_id=leg.account, now=parent.ts)  # type: ignore[arg-type]
    sink = JsonlSink(Path(state_dir) / "risk-audit.jsonl") if state_dir else None
    return RiskGate(limits=LIMITS, envelope=L.ENVELOPE, breakers=breakers, sink=sink)


def gate_leg(
    gate: RiskGate, lg: L.Ledger, intent: Intent, now: float
) -> tuple[bool, Decimal, str, bool]:
    """THE gate for every leg on every path: (allowed, approved notional, reason, clamped)."""
    if intent.kind == "exit":
        gate.approve_order(
            kind="exit", value=intent.notional, deployment_id=intent.account, now=now
        )
        return True, intent.notional, "exit — privileged, never blocked or clamped", False
    if lg.kill.get("engaged"):
        return False, Decimal(0), "kill switch engaged — entry blocked", False
    book = lg.books[intent.account]
    if book.exhausted:
        return (
            False,
            Decimal(0),
            f"sleeve equity {book.equity} USD below minimum stake + fee",
            False,
        )
    d = gate.approve_order(
        kind="entry",
        value=intent.notional,
        daily_pnl=B.day_pnl(book, B.today(now)),
        deployment_id=intent.account,
        ticker=B.INSTRUMENT,
        now=now,
    )
    if not d.allowed:
        why = {
            "max_daily_loss": f"daily-loss envelope (−{L.ENVELOPE.max_daily_loss} USD) exhausted",
        }.get(d.reason or "", f"rate breaker: {d.reason}")
        return False, Decimal(0), why, False
    approved = Decimal(d.approved_value or 0)
    if approved != intent.notional:
        return (
            True,
            approved,
            f"size clamped {intent.notional} → {approved} USD (max order value)",
            True,
        )
    return True, approved, "within limits", False


def _legs_for(path: str, intents: list[Intent], max_clip: Decimal | None) -> list[Intent]:
    if path == "single":
        if len(intents) != 1:
            raise TicketError("single takes exactly one order")
        return intents
    if path == "broadcast":
        accounts = [i.account for i in intents]
        if len(set(accounts)) != len(accounts) or not intents:
            raise TicketError("broadcast needs one or more distinct accounts")
        return intents
    if path == "basket":
        if not intents:
            raise TicketError("basket needs at least one order")
        return intents
    if path == "split":
        if len(intents) != 1:
            raise TicketError("split takes exactly one order")
        if max_clip is None or max_clip <= 0:
            raise TicketError("split needs a max clip > 0 USD")
        base, out, left = intents[0], [], intents[0].notional
        while left > 0:
            clip = min(max_clip, left)
            out.append(Intent(base.account, base.side, clip, base.kind))
            left -= clip
        return out
    raise TicketError(f"path must be one of {PATHS}")


def broadcast(
    account_list: Iterable[str], side: str, notional: Decimal, kind: str = "entry"
) -> list[Intent]:
    """Fan one order out to N accounts (one intent per account)."""
    return [Intent(a, side, notional, kind) for a in account_list]


def submit(
    lg: L.Ledger,
    path: str,
    intents: list[Intent],
    *,
    now: float,
    max_clip: Decimal | None = None,
    bracket: bool = False,
    gate: RiskGate | None = None,
    state_dir: str | None = None,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> Parent:
    """Route a ticket down one path; every leg through :func:`gate_leg`; journal it."""
    if bracket:
        raise TicketError(BRACKET_UNSUPPORTED)
    legs_in = _legs_for(path, intents, max_clip)
    if gate is None:
        gate = make_gate(load(state_dir) if state_dir else [], state_dir)
    pid = new_id()
    expiry = (now // INTERVAL_S + 1) * INTERVAL_S
    parent = Parent(pid, path, now, B.INSTRUMENT, expiry, state="")
    for n, it in enumerate(legs_in, 1):
        ok, approved, why, clamped = gate_leg(gate, lg, it, now)
        leg = Leg(
            id=f"{pid}-{n}",
            parent_id=pid,
            seq=n,
            account=it.account,
            side=it.side,
            kind=it.kind,
            requested=str(it.notional),
            status="filled" if ok else "blocked",
            reason=why,
        )
        if ok:
            leg.notional = str(approved)
            leg.qty = int(approved / L.FILL_PRICE)
            leg.price = str(L.FILL_PRICE)
            leg.fee = str(L.fee_for(approved))
            leg.clamped = clamped
        parent.legs.append(leg)
    sent = sum(1 for x in parent.legs if x.status == "filled")
    parent.state = classify_broadcast(len(parent.legs), sent, 0) if sent else "rejected"
    if state_dir:
        _append(state_dir, parent)
    return parent


def parse_money(raw: str | None, what: str = "notional") -> Decimal:
    try:
        v = Decimal((raw or "").strip())
    except InvalidOperation:
        raise TicketError(f"{what} must be a number of USD") from None
    if not v.is_finite() or v <= 0:
        raise TicketError(f"{what} must be > 0 USD")
    return v.quantize(L.CENT)


def parse_basket(text: str, kind: str = "entry") -> list[Intent]:
    """One order per line: ``account side notional`` (e.g. ``laya YES 10``)."""
    out = []
    for n, line in enumerate((text or "").splitlines(), 1):
        parts = line.split()
        if not parts:
            continue
        if len(parts) != 3:
            raise TicketError(f"basket line {n}: expected 'account side notional'")
        out.append(Intent(parts[0].lower(), parts[1].upper(), parse_money(parts[2]), kind))
    return out


def narrow(parents: list[Parent], accounts: Iterable[str]) -> list[Parent]:
    """Parents with only the legs on ``accounts``; parents left with none are dropped."""
    keep = set(accounts)
    out = []
    for p in parents:
        legs = [x for x in p.legs if x.account in keep]
        if legs:
            out.append(replace(p, legs=legs))
    return out


def blotter_rows(
    parents: list[Parent], account: str = B.ALL, status: str | None = None
) -> list[dict]:
    """Ticket legs as blotter lines (same shape as ``blotter.orders`` + parent fields)."""
    out = []
    for p in parents:
        for leg in p.legs:
            if account != B.ALL and leg.account != account:
                continue
            if status is not None and leg.status != status:
                continue
            out.append(
                {
                    "ts": p.ts,
                    "account": leg.account,
                    "instrument": p.instrument,
                    "side": leg.side,
                    "qty": leg.qty,
                    "requested": leg.requested,
                    "notional": leg.notional,
                    "price": leg.price,
                    "fee": leg.fee,
                    "pnl": None,  # settles at the interval close; not scored in the PoC
                    "status": leg.status,
                    "clamped": leg.clamped,
                    "reason": leg.reason,
                    "source": "ticket",
                    "parent_id": leg.parent_id,
                    "leg_id": leg.id,
                    "path": p.path,
                    "kind": leg.kind,
                    "parent_state": p.state,
                }
            )
    return out
