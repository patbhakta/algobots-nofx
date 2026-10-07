"""Demo account registry, execution-adapter seam and order-ticket broadcast (ALG-3266).

Fincept R2 + OpenAlgo per-account execution on top of the S4.1 registry
(``accounts``) and the S4.3 approval queue (``approval_requests`` +
append-only ``action_ledger``):

- every account carries its own environment (``mode`` paper|live) and
  approval mode (``approval_mode`` auto|semi_auto);
- one order ticket broadcasts a leg to each selected account. Auto PAPER
  legs fill through the paper adapter, Semi-auto legs park in the approval
  queue, LIVE legs are refused before an order row exists. The ticket's
  state folds through ``classify_broadcast`` (``part_queued`` when some
  legs filled and some parked);
- approving a parked leg fills it through the same paper adapter and
  ledgers the verdict and the fill.

Adapter seam: ``ADAPTERS`` maps a venue key to an ``ExecutionAdapter``.
Only ``paper`` is registered. The OpenAlgo bridge (ALG-3129) registers here
later; LIVE accounts stay refused regardless until G-live passes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from algobots.api.accounts.models import AccountCredential
from algobots.api.approvals.models import ActionLedger, ApprovalRequest, ApprovalStatus, Broadcast
from algobots.api.approvals.service import (
    append_ledger,
    classify_broadcast,
    decide_request,
    expire_overdue,
    park_order,
    parks,
    report_broadcast,
)
from algobots.api.models import DEMO_OWNER_EMAIL, Account, Order, User
from algobots.demo import ledger as L

LIVE_GATE_REASON = "live gated: G-live not passed"
SYMBOL = "KXBTC15M"
PARK_TTL_S = 3600  # an hour for a human to act before the leg expires

# label -> (broker, mode, approval_mode, status, ledger strategy key or None)
SEED: dict[str, tuple[str, str, str, str, str | None]] = {
    L.STRATEGIES["laya"]: ("kalshi", "paper", "auto", "active", "laya"),
    L.STRATEGIES["jev"]: ("kalshi", "paper", "auto", "active", "jev"),
    L.STRATEGIES["coin"]: ("kalshi", "paper", "auto", "active", "coin"),
    "Pat · Kalshi semi-auto": ("kalshi", "paper", "semi_auto", "active", None),
    "Pat · Kalshi live": ("kalshi", "live", "auto", "paused", None),
}


class LiveGated(Exception):
    """A LIVE account was asked to execute; refused until G-live passes."""


@dataclass(frozen=True)
class Fill:
    qty: float
    price: float
    venue: str


class ExecutionAdapter(Protocol):
    """The seam a venue bridge implements. ``submit`` returns the fill or raises."""

    venue: str

    def submit(self, order: Order) -> Fill: ...


class PaperAdapter:
    """Simulated fill at the assumed 50c mid, same as the paper ledger."""

    venue = "paper"

    def submit(self, order: Order) -> Fill:
        return Fill(qty=order.qty, price=float(L.FILL_PRICE), venue=self.venue)


ADAPTERS: dict[str, ExecutionAdapter] = {"paper": PaperAdapter()}


def register_adapter(adapter: ExecutionAdapter) -> None:
    """Plug a venue bridge in (OpenAlgo, ALG-3129). Does not lift the LIVE gate."""
    ADAPTERS[adapter.venue] = adapter


def adapter_for(account: Account) -> ExecutionAdapter:
    """The adapter that may execute for ``account``; LIVE always raises ``LiveGated``."""
    if account.mode != "paper":
        raise LiveGated(LIVE_GATE_REASON)
    return ADAPTERS["paper"]


def environment(account: Account) -> str:
    return "PAPER" if account.mode == "paper" else "LIVE"


def order_block_reason(account: Account) -> str | None:
    """Why order actions on this account are disabled (None = enabled)."""
    if account.mode != "paper":
        return LIVE_GATE_REASON
    if account.status != "active":
        return f"account {account.status}"
    return None


# --- registry ------------------------------------------------------------------------


def ensure_seeded(db: Session) -> User:
    """Idempotently create the demo registry owner and its accounts (all PAPER but one)."""
    owner = db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    if owner is None:
        owner = User(
            email=DEMO_OWNER_EMAIL,
            password_hash="!",  # not a scrypt hash: verify_password always fails
            display_name="Demo registry",
            is_active=False,
        )
        db.add(owner)
        try:
            db.commit()
        except IntegrityError:  # a concurrent request seeded it first
            db.rollback()
            owner = db.scalar(select(User).where(User.email == DEMO_OWNER_EMAIL))
    have = set(db.scalars(select(Account.label).where(Account.user_id == owner.id)))
    missing = [label for label in SEED if label not in have]
    for label in missing:
        broker, mode, approval, status, _ = SEED[label]
        db.add(
            Account(
                user_id=owner.id,
                label=label,
                broker=broker,
                mode=mode,
                approval_mode=approval,
                status=status,
            )
        )
    if missing:
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
    return owner


def accounts(db: Session, owner: User) -> list[Account]:
    order = {label: i for i, label in enumerate(SEED)}
    rows = db.scalars(select(Account).where(Account.user_id == owner.id))
    return sorted(rows, key=lambda a: (order.get(a.label, len(order)), a.label))


def session_health(db: Session, account: Account) -> tuple[str, str]:
    """(status kind, text) from stored credentials; paper needs none."""
    cred = db.scalar(select(AccountCredential).where(AccountCredential.account_id == account.id))
    if cred is not None:
        kind = "connected" if cred.token_status == "active" else "expired"
        return kind, f"token {cred.token_status}"
    if account.mode == "paper":
        return "connected", "paper adapter"
    return "disconnected", "no credentials"


def strategy_key(account: Account) -> str | None:
    seed = SEED.get(account.label)
    return seed[4] if seed else None


# --- order ticket broadcast ----------------------------------------------------------


@dataclass
class Leg:
    account_id: UUID
    label: str
    status: str  # filled | parked | blocked
    reason: str
    order_id: UUID | None = None
    request_id: UUID | None = None


@dataclass
class Ticket:
    id: UUID
    side: str
    qty: float
    state: str
    legs: list[Leg] = field(default_factory=list)


def broadcast(
    db: Session,
    owner: User,
    account_ids: list[UUID],
    *,
    side: str,
    qty: float,
    actor: str,
    halts: dict[UUID, str] | None = None,
) -> Ticket:
    """Send one ticket to each account: fill (auto), park (semi-auto) or refuse (LIVE).

    ``halts`` maps account id -> why it is halted (kill switch, sleeve, daily cap);
    those legs are refused with that reason, same rails as the strategy ledger.
    """
    ticket = Ticket(id=uuid4(), side=side, qty=qty, state="")
    for account_id in account_ids:
        account = db.get(Account, account_id)
        if account is None or account.user_id != owner.id:
            continue
        block = order_block_reason(account) or (halts or {}).get(account.id)
        if block:
            ticket.legs.append(Leg(account.id, account.label, "blocked", block))
            continue
        order = Order(
            user_id=owner.id,
            account_id=account.id,
            symbol=f"{SYMBOL}:{side}",  # Kalshi: buy the YES or the NO contract
            side="buy",
            order_type="market",
            qty=qty,
            status="parked" if parks(account) else "pending",
        )
        db.add(order)
        db.flush()
        if parks(account):
            req = park_order(
                db,
                order,
                ttl_seconds=PARK_TTL_S,
                reason=f"semi-auto account: {side} leg queued for approval",
            )
            ticket.legs.append(
                Leg(account.id, account.label, "parked", "awaiting approval", order.id, req.id)
            )
            continue
        fill = adapter_for(account).submit(order)
        order.status = "filled"
        ticket.legs.append(
            Leg(
                account.id,
                account.label,
                "filled",
                f"{fill.qty:g} {side} @ {fill.price:.2f} via {fill.venue} adapter",
                order.id,
            )
        )
    sent = sum(qty for leg in ticket.legs if leg.status == "filled")
    queued = sum(qty for leg in ticket.legs if leg.status == "parked")
    total = qty * len(ticket.legs)
    ticket.state = classify_broadcast(total, sent, queued) if sent or queued else "blocked"
    append_ledger(
        db,
        user_id=owner.id,
        action="ticket_broadcast",
        subject_type="ticket",
        subject_id=ticket.id,
        actor_id=owner.id,
        reason=f"{ticket.state} · by {actor}",
        detail={
            "symbol": SYMBOL,
            "side": side,
            "qty": qty,
            "state": ticket.state,
            "legs": [
                {
                    "account": leg.label,
                    "status": leg.status,
                    "reason": leg.reason,
                    "order_id": str(leg.order_id) if leg.order_id else None,
                    "request_id": str(leg.request_id) if leg.request_id else None,
                }
                for leg in ticket.legs
            ],
        },
    )
    db.commit()
    return ticket


def decide(
    db: Session, owner: User, request_id: UUID, verdict: str, *, actor: str
) -> tuple[ApprovalRequest, Broadcast | None]:
    """Approve (paper-fill) or reject one parked leg; both land in the action ledger."""
    req = db.get(ApprovalRequest, request_id)
    if req is None or req.user_id != owner.id:
        raise LookupError("approval request not found")
    req = decide_request(db, owner, req, verdict, f"{verdict} by {actor}")
    if verdict != ApprovalStatus.APPROVED.value:
        return req, None
    order = db.get(Order, req.order_id)
    fill = adapter_for(db.get(Account, req.account_id)).submit(order)
    order.status = "filled"
    out = report_broadcast(
        db,
        owner,
        req,
        sent_qty=fill.qty,
        queued_qty=0,
        reason=f"approved leg filled {fill.qty:g} @ {fill.price:.2f} via {fill.venue} adapter",
    )
    return req, out


def pending(db: Session, owner: User) -> list[ApprovalRequest]:
    expire_overdue(db, owner)
    return list(
        db.scalars(
            select(ApprovalRequest)
            .where(
                ApprovalRequest.user_id == owner.id,
                ApprovalRequest.status == ApprovalStatus.PARKED.value,
            )
            .order_by(ApprovalRequest.parked_at.desc())
        )
    )


def ledger_tail(db: Session, owner: User, limit: int = 8) -> list[ActionLedger]:
    return list(
        db.scalars(
            select(ActionLedger)
            .where(ActionLedger.user_id == owner.id)
            .order_by(ActionLedger.created_at.desc(), ActionLedger.id.desc())
            .limit(limit)
        )
    )


def last_ticket(db: Session, owner: User) -> dict | None:
    row = db.scalar(
        select(ActionLedger)
        .where(ActionLedger.user_id == owner.id, ActionLedger.action == "ticket_broadcast")
        .order_by(ActionLedger.created_at.desc(), ActionLedger.id.desc())
        .limit(1)
    )
    return {**json.loads(row.detail_json), "at": row.created_at} if row else None
