"""Order ticket: one paper order type, five paths, one risk gate (Fincept R1).

Paths (study ``alg-3070-fincept-terminal-feasibility.md`` §3 R1):

- ``single``    — one account.
- ``broadcast`` — one order fanned to N accounts, one result per account
                  (Fincept ``broadcast_order``).
- ``basket``    — several orders submitted as one unit.
- ``split``     — one order chunked under a max clip
                  (Fincept ``place_order_auto_split``).
- ``bracket``   — per account, an entry plus a take-profit and a stop exit
                  child (ALG-3262). The children rest as a one-cancels-other
                  pair once the entry fills; cancelling the parent cancels
                  every child still working.

Every path builds a parent of legs and every leg goes through :func:`gate_leg`,
which calls ``gate.pre_trade`` — the same check the strategy decisions and the
registry broadcast use: account mode (LIVE hard-disabled) -> demo kill switch
-> sleeve floor -> ``risk.RiskGate`` (daily-loss envelope, rate breakers,
order-value clamp) -> affordability. Exits are privileged: nothing blocks or
shrinks an exit. A denied leg records the stated reason.

Bracket children are resting orders, so they are gated on a dry-run copy of the
gate: they pass the same checks but only consume breaker budget if they trigger.
No order book is captured, so in this PoC they never trigger; they stay
``working`` until cancelled or the contract settles.

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
from algobots.demo import gate as G
from algobots.demo import ledger as L
from algobots.risk import JsonlSink, RateBreakers, RiskGate, RiskLimits

PATHS = ("single", "broadcast", "basket", "split", "bracket")
SIDES = ("YES", "NO")
KINDS = ("entry", "exit")
INTERVAL_S = 15 * 60
BRACKET_NOTE = (
    "bracket: take-profit + stop rest as a one-cancels-other pair after the entry fills; "
    "no order book is captured, so they only end by cancel or the 15m settlement"
)
CANCEL_CASCADE = "parent cancelled — cascade"
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
    status: str  # filled / blocked / working (bracket child) / cancelled
    reason: str
    notional: str = "0"
    qty: int = 0
    price: str | None = None
    fee: str = "0"
    clamped: bool = False
    role: str = "order"  # order / entry / take_profit / stop


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
    cancelled_ts: float | None = None


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
    if state_dir:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
    return RiskGate(limits=LIMITS, envelope=L.ENVELOPE, breakers=breakers, sink=sink)


def gate_leg(
    gate: RiskGate, lg: L.Ledger, intent: Intent, now: float, path: str = "single"
) -> tuple[bool, Decimal, str, bool]:
    """THE gate for every leg on every path: (allowed, approved notional, reason, clamped).

    A thin adapter onto ``gate.pre_trade`` (looked up on the module, so a spy
    patched there sees every ticket leg).
    """
    book = lg.books[intent.account]
    g = G.pre_trade(
        G.GateRequest(
            account=intent.account,
            path=path,
            value=intent.notional,
            equity=book.equity,
            floor=L.MIN_STAKE + L.fee_for(L.MIN_STAKE),  # == StrategyBook.exhausted
            daily_pnl=B.day_pnl(book, B.today(now)),
            kill_engaged=bool(lg.kill.get("engaged")),
            kind=intent.kind,
            now=now,
            ticker=B.INSTRUMENT,
            fee=L.fee_for if intent.kind == "entry" else None,
        ),
        gate,
    )
    if not g.allowed:
        return False, Decimal(0), g.reason, False
    if intent.kind == "exit":
        return True, g.approved, "exit — privileged, never blocked or clamped", False
    if g.approved != intent.notional:
        why = g.reason or f"size cut {intent.notional} → {g.approved} USD (sleeve can pay)"
        return True, g.approved, why, True
    return True, g.approved, "within limits", False


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
    if path == "bracket":
        accounts = [i.account for i in intents]
        if len(set(accounts)) != len(accounts) or not intents:
            raise TicketError("bracket needs one or more distinct accounts")
        if any(i.kind != "entry" for i in intents):
            raise TicketError("a bracket opens with an entry")
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


def parse_price(raw: str | None, what: str) -> Decimal:
    try:
        v = Decimal((raw or "").strip())
    except InvalidOperation:
        raise TicketError(f"{what} must be a contract price") from None
    if not v.is_finite() or not Decimal("0.01") <= v <= Decimal("0.99"):
        raise TicketError(f"{what} must be 0.01–0.99")
    return v.quantize(L.CENT)


def _leg(pid: str, n: int, it: Intent, gated: tuple[bool, Decimal, str, bool], role: str) -> Leg:
    ok, approved, why, clamped = gated
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
        role=role,
    )
    if ok:
        leg.notional = str(approved)
        leg.qty = int(approved / L.FILL_PRICE)
        leg.price = str(L.FILL_PRICE)
        leg.fee = str(L.fee_for(approved))
        leg.clamped = clamped
    return leg


def _children(
    pid: str,
    n: int,
    gate: RiskGate,
    lg: L.Ledger,
    entry: Leg,
    tp: Decimal,
    stop: Decimal,
    now: float,
) -> list[Leg]:
    """Take-profit + stop for a filled bracket entry: gated (dry run), then resting."""
    probe = G.dry_run(gate)  # resting orders: checked now, breaker budget spent on trigger
    out = []
    for role, px in (("take_profit", tp), ("stop", stop)):
        n += 1
        it = Intent(entry.account, entry.side, Decimal(entry.notional), "exit")
        leg = _leg(pid, n, it, gate_leg(probe, lg, it, now, "bracket"), role)
        if leg.status == "filled":
            leg.status, leg.price, leg.fee = "working", str(px), "0"
            label = role.replace("_", "-")
            leg.reason = f"{label} @ {px} · OCO with leg {entry.seq} · {leg.reason}"
        out.append(leg)
    return out


def submit(
    lg: L.Ledger,
    path: str,
    intents: list[Intent],
    *,
    now: float,
    max_clip: Decimal | None = None,
    take_profit: Decimal | None = None,
    stop: Decimal | None = None,
    gate: RiskGate | None = None,
    state_dir: str | None = None,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> Parent:
    """Route a ticket down one path; every leg through :func:`gate_leg`; journal it."""
    legs_in = _legs_for(path, intents, max_clip)
    if path == "bracket":
        if take_profit is None or stop is None:
            raise TicketError("bracket needs a take-profit and a stop price")
        if not stop < L.FILL_PRICE < take_profit:
            raise TicketError(
                f"bracket prices must straddle the {L.FILL_PRICE} fill: stop < fill < take-profit"
            )
    if gate is None:
        gate = make_gate(load(state_dir) if state_dir else [], state_dir)
    pid = new_id()
    expiry = (now // INTERVAL_S + 1) * INTERVAL_S
    parent = Parent(pid, path, now, B.INSTRUMENT, expiry, state="")
    if path == "bracket":
        parent.note = f"{PAPER_NOTE} · {BRACKET_NOTE}"
    for it in legs_in:
        n = len(parent.legs) + 1
        role = "entry" if path == "bracket" else "order"
        leg = _leg(pid, n, it, gate_leg(gate, lg, it, now, path), role)
        parent.legs.append(leg)
        if path == "bracket" and leg.status == "filled":
            parent.legs += _children(pid, n, gate, lg, leg, take_profit, stop, now)  # type: ignore[arg-type]
    heads = [x for x in parent.legs if x.role in ("order", "entry")]
    sent = sum(1 for x in heads if x.status == "filled")
    parent.state = classify_broadcast(len(heads), sent, 0) if sent else "rejected"
    if state_dir:
        _append(state_dir, parent)
    return parent


def cancel(state_dir: str, parent_id: str, *, now: float) -> Parent:
    """Cancel a ticket: every child still ``working`` is cancelled with it (cascade).

    Fills are final, so filled legs stay filled. Rewrites the journal in place.
    """
    parents = load(state_dir)
    hit = next((p for p in parents if p.id == parent_id), None)
    if hit is None:
        raise TicketError(f"unknown ticket {parent_id!r}")
    if hit.cancelled_ts is None:
        hit.cancelled_ts = now
        for leg in hit.legs:
            if leg.status == "working":
                leg.status, leg.reason = "cancelled", f"{CANCEL_CASCADE} ({leg.reason})"
        p = _path(state_dir)
        tmp = p.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(asdict(x)) + "\n" for x in parents), encoding="utf-8")
        tmp.replace(p)
    return hit


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
                    "role": leg.role,
                    "parent_state": p.state,
                }
            )
    return out
