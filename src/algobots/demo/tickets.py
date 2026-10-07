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
shrinks an exit. A denied leg records the stated reason and its typed
``denial_code``.

Execution (ALG-3263): a ``dispatch`` callback turns every allowed leg into a
request for that account's Nautilus paper worker
(``algobots.demo.orderapi`` enqueues it; the worker executes it and appends a
``fill`` record here). Dispatched legs rest at ``submitted`` until the worker
fills them; without a callback (unit tests) the legacy in-process paper fill
stands in. Bracket children are resting orders, so they are gated on a dry-run
copy of the gate and stay ``working`` regardless — no order book is captured,
so they only end by cancel or the interval settlement.

The journal ``ticket-orders.jsonl`` is append-only and holds mixed records:
``parent`` snapshots (the submission), ``fill`` / ``reject`` patches from the
worker and ``cancel`` patches from the API. :func:`load` folds them in order,
and fills are final — a cancel never overwrites a leg the worker already
filled. Rate-breaker state is rebuilt from the fold on every submit, so the
gate is deterministic and survives restarts.
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
DISPATCHED = ("submitted", "filled")  # a dispatched leg reached / will reach its worker
BRACKET_NOTE = (
    "bracket: take-profit + stop rest as a one-cancels-other pair after the entry fills; "
    "no order book is captured, so they only end by cancel or the 15m settlement"
)
CANCEL_CASCADE = "parent cancelled — cascade"
CANCEL_BEFORE_RUN = "cancelled before the worker executed it"
PAPER_NOTE = (
    f"paper only · executed by the account's Nautilus paper worker at the assumed "
    f"{L.FILL_PRICE} mid + Kalshi taker fee (no order book captured)"
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
    status: str  # submitted / filled / blocked / working (bracket child) / cancelled
    reason: str
    notional: str = "0"
    qty: int = 0
    price: str | None = None
    fee: str = "0"
    clamped: bool = False
    role: str = "order"  # order / entry / take_profit / stop
    denial_code: str | None = None  # typed gate reason when blocked
    filled_ts: float | None = None
    worker_trader_id: str | None = None  # the executing worker's Nautilus trader id
    worker_order_id: str | None = None  # its client order id (embeds the account tag)
    worker_trade_id: str | None = None
    venue_account_id: str | None = None


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


def journal_path(state_dir: str) -> Path:
    return Path(state_dir) / "ticket-orders.jsonl"


def _write_event(p: Path, rec: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec) + "\n")


def load(state_dir: str) -> list[Parent]:
    """Fold the append-only journal: parents, then worker fills/rejects, then cancels."""
    p = journal_path(state_dir)
    if not p.exists():
        return []
    by_id: dict[str, Parent] = {}
    for line in p.read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not isinstance(d, dict):
            continue
        rec = d.pop("rec", None)  # absent: a pre-ALG-3263 plain parent record
        if rec in (None, "parent"):
            try:
                d["legs"] = [Leg(**x) for x in d["legs"]]
                by_id[d["id"]] = Parent(**d)
            except (ValueError, TypeError, KeyError):
                continue
        elif d.get("parent") in by_id:
            _patch(by_id[d["parent"]], rec, d)
    return list(by_id.values())


def _patch(parent: Parent, rec: str, d: dict) -> None:
    """Apply one journal patch in place; fills are final and never overwritten."""
    if rec == "cancel":
        ids = d.get("legs")  # None: the whole parent (legacy cascade)
        for leg in parent.legs:
            if leg.status in ("working", "submitted") and (ids is None or leg.id in ids):
                was, leg.status = leg.status, "cancelled"
                leg.reason = (
                    f"{CANCEL_BEFORE_RUN} ({leg.reason})"
                    if was == "submitted"
                    else f"{CANCEL_CASCADE} ({leg.reason})"
                )
        if d.get("full"):
            parent.cancelled_ts = d.get("ts")
        return
    for leg in parent.legs:
        if leg.id != d.get("leg"):
            continue
        if rec == "fill":
            if leg.status == "filled":
                continue
            leg.status = "filled"
            if d.get("notional") is not None:
                leg.notional = str(d["notional"])
            leg.qty = int(Decimal(str(d.get("qty", leg.qty))))
            leg.price = str(d.get("price", leg.price))
            leg.fee = str(d.get("fee", leg.fee))
            leg.filled_ts = d.get("ts")
            leg.worker_trader_id = d.get("trader_id")
            leg.worker_order_id = d.get("client_order_id")
            leg.worker_trade_id = d.get("trade_id")
            leg.venue_account_id = d.get("venue_account_id")
        elif rec == "reject" and leg.status == "submitted":
            leg.status, leg.reason = "blocked", f"venue rejected — {d.get('reason', 'unknown')}"


def append_event(state_dir: str, rec: dict) -> None:
    """Append one ``fill`` / ``reject`` / ``cancel`` patch (worker and API side)."""
    _write_event(journal_path(state_dir), {**rec, "rec": rec.get("rec", "fill")})


def _append(state_dir: str, parent: Parent) -> None:
    _write_event(journal_path(state_dir), {"rec": "parent", **asdict(parent)})


def make_gate(history: Iterable[Parent], state_dir: str | None = None) -> RiskGate:
    """A RiskGate whose breakers have replayed every journaled dispatched leg.

    Dispatched (``filled`` or still-``submitted``) legs both count: an order
    queued for a worker has been sent, rate-wise, the moment it passed here.
    """
    breakers = RateBreakers(clock=lambda: 0.0)
    for parent in history:
        for leg in parent.legs:
            if leg.status in DISPATCHED:
                breakers.record(leg.kind, deployment_id=leg.account, now=parent.ts)  # type: ignore[arg-type]
    sink = JsonlSink(Path(state_dir) / "risk-audit.jsonl") if state_dir else None
    if state_dir:
        Path(state_dir).mkdir(parents=True, exist_ok=True)
    return RiskGate(limits=LIMITS, envelope=L.ENVELOPE, breakers=breakers, sink=sink)


def gate_leg(
    gate: RiskGate, lg: L.Ledger, intent: Intent, now: float, path: str = "single"
) -> tuple[bool, Decimal, str, bool, str | None]:
    """THE gate for every leg on every path: (allowed, approved, reason, clamped, code).

    A thin adapter onto ``gate.pre_trade`` (looked up on the module, so a spy
    patched there sees every ticket leg). ``code`` is the typed denial reason
    (``kill_switch``, ``max_daily_loss``, …) or None when allowed.
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
        return False, Decimal(0), g.reason, False, g.code
    if intent.kind == "exit":
        return True, g.approved, "exit — privileged, never blocked or clamped", False, None
    if g.approved != intent.notional:
        why = g.reason or f"size cut {intent.notional} → {g.approved} USD (sleeve can pay)"
        return True, g.approved, why, True, None
    return True, g.approved, "within limits", False, None


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


def _leg(
    pid: str,
    n: int,
    it: Intent,
    gated: tuple[bool, Decimal, str, bool, str | None],
    role: str,
    submitted: bool = False,
) -> Leg:
    ok, approved, why, clamped, code = gated
    status = "submitted" if ok and submitted else ("filled" if ok else "blocked")
    leg = Leg(
        id=f"{pid}-{n}",
        parent_id=pid,
        seq=n,
        account=it.account,
        side=it.side,
        kind=it.kind,
        requested=str(it.notional),
        status=status,
        reason=why,
        role=role,
        denial_code=code if not ok else None,
    )
    if ok:
        leg.notional = str(approved)
        leg.qty = int(approved / L.FILL_PRICE)
        leg.clamped = clamped
        if status == "filled":  # the legacy in-process paper fill; a worker overwrites this
            leg.price = str(L.FILL_PRICE)
            leg.fee = str(L.fee_for(approved))
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
        if leg.status in ("filled", "submitted"):
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
    dispatch: Callable[[Parent, Leg], None] | None = None,
    new_id: Callable[[], str] = lambda: uuid.uuid4().hex[:12],
) -> Parent:
    """Route a ticket down one path; every leg through :func:`gate_leg`; journal it.

    ``dispatch(parent, leg)`` hands every allowed leg to its account's worker
    (ALG-3263): the leg rests ``submitted`` until the worker's ``fill`` record
    lands in the journal. Without it the legacy in-process paper fill stands in.
    """
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
        leg = _leg(pid, n, it, gate_leg(gate, lg, it, now, path), role, dispatch is not None)
        parent.legs.append(leg)
        if path == "bracket" and leg.status in DISPATCHED:
            parent.legs += _children(pid, n, gate, lg, leg, take_profit, stop, now)  # type: ignore[arg-type]
    heads = [x for x in parent.legs if x.role in ("order", "entry")]
    sent = sum(1 for x in heads if x.status in DISPATCHED)
    parent.state = classify_broadcast(len(heads), sent, 0) if sent else "rejected"
    if state_dir:
        _append(state_dir, parent)
    if dispatch is not None:
        for leg in parent.legs:
            if leg.status == "submitted":
                dispatch(parent, leg)
    return parent


def cancel(
    state_dir: str, parent_id: str, *, now: float, accounts: Iterable[str] | None = None
) -> Parent:
    """Cancel a ticket's live legs (``working`` / ``submitted``); fills stay final.

    The whole parent by default; ``accounts`` narrows the blast radius to those
    accounts' legs (the v1 ``cancel-all`` per account). Appends a ``cancel``
    record — the worker drops any not-yet-executed request it finds cancelled.
    """
    hit = next((p for p in load(state_dir) if p.id == parent_id), None)
    if hit is None:
        raise TicketError(f"unknown ticket {parent_id!r}")
    ids: list[str] | None = None
    if accounts is not None:
        keep = set(accounts)
        ids = [x.id for x in hit.legs if x.account in keep]
        if not ids:
            return hit  # none of this account's legs are on that parent
    append_event(
        state_dir,
        {"rec": "cancel", "parent": parent_id, "legs": ids, "ts": now, "full": ids is None},
    )
    return next(p for p in load(state_dir) if p.id == parent_id)


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
                    "denial_code": leg.denial_code,
                    "filled_ts": leg.filled_ts,
                    "source": "ticket",
                    "parent_id": leg.parent_id,
                    "leg_id": leg.id,
                    "path": p.path,
                    "kind": leg.kind,
                    "role": leg.role,
                    "parent_state": p.state,
                    "worker_trader_id": leg.worker_trader_id,
                    "worker_order_id": leg.worker_order_id,
                    "worker_trade_id": leg.worker_trade_id,
                    "venue_account_id": leg.venue_account_id,
                }
            )
    return out
