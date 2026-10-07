"""Approval queue service: parking rule, state machine, latency, ledger (S4.3).

Parking rule (paper-only standing law): an order whose account `mode` is
`semi_auto` is bound for live routing, so it never reaches a broker. It is
recorded as `parked` and waits for a human verdict via `decide_request`.
No live entitlement is created by this module — approving only releases the
order row for downstream (paper) dispatch.

State machine: `parked -> approved | rejected | expired`. Every other
transition raises `ApprovalError` (4xx); the test matrix in
tests/approvals/ proves each legal path and rejects each illegal one.

Latency: every decision records `latency_ms` = park -> decision timestamps,
persisted on the request AND in the append-only ledger row for that action.
Expiry records the same measure at sweep time.

Ledger discipline: `append_ledger` is the ONLY writer to `action_ledger`;
rows carry actor, reason, and latency, and are never updated or deleted
(the database itself rejects UPDATE/DELETE — migration 0004 triggers).

Logging discipline: structured, secret-free events (`order_parked`,
`approval_decided`, ...) — ids, symbols, states, latencies only.
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from algobots.api.approvals.models import (
    ActionLedger,
    ApprovalRequest,
    ApprovalStatus,
    Broadcast,
    BroadcastState,
)
from algobots.api.models import Account, Order, User

logger = logging.getLogger("algobots.api.approvals.service")

SEMI_AUTO = "semi_auto"
PARK_TTL_SECONDS = 300
PARK_REASON = "semi_auto account: live-bound order parked for human approval"
EXPIRY_REASON = "parked request expired before a human verdict"

# Legal state-machine edges. `expired` is reachable only via the expiry path
# (sweep of overdue parked requests), never via the decide endpoint.
LEGAL_TRANSITIONS: dict[str, set[str]] = {
    ApprovalStatus.PARKED.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.EXPIRED.value,
    },
}

# Order-row status each verdict maps onto (parked orders never bypass the queue).
VERDICT_ORDER_STATUS = {
    ApprovalStatus.APPROVED.value: "submitted",
    ApprovalStatus.REJECTED.value: "cancelled",
    ApprovalStatus.EXPIRED.value: "cancelled",
}


class ApprovalError(Exception):
    """Domain failure with an HTTP status and a clear, user-facing message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _utcnow() -> datetime:
    return datetime.now(UTC)


def aware_utc(value: datetime) -> datetime:
    """Coerce a read-back datetime to UTC-aware.

    SQLite (the paper/test dialect) returns naive datetimes even for
    `DateTime(timezone=True)` columns; every value this module writes is
    UTC, so restoring the tzinfo is lossless and keeps latency math sound.
    """
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _latency_ms(start: datetime, end: datetime) -> int:
    return max(0, round((aware_utc(end) - aware_utc(start)).total_seconds() * 1000))


# --- ledger -----------------------------------------------------------------------


def append_ledger(
    db: Session,
    *,
    user_id: UUID,
    action: str,
    subject_type: str,
    subject_id: UUID,
    actor_id: UUID | None = None,
    reason: str = "",
    latency_ms: int | None = None,
    detail: dict | None = None,
) -> ActionLedger:
    """Append one immutable action row. The only writer to `action_ledger`."""
    row = ActionLedger(
        user_id=user_id,
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        actor_id=actor_id,
        reason=reason,
        latency_ms=latency_ms,
        detail_json=json.dumps(detail or {}, sort_keys=True, separators=(",", ":")),
    )
    db.add(row)
    return row


def list_ledger(db: Session, user: User, limit: int = 200) -> list[ActionLedger]:
    """The caller's ledger tail, newest first."""
    return list(
        db.scalars(
            select(ActionLedger)
            .where(ActionLedger.user_id == user.id)
            .order_by(ActionLedger.created_at.desc(), ActionLedger.id.desc())
            .limit(min(limit, 1000))
        )
    )


# --- parking ----------------------------------------------------------------------


def parks(account: Account) -> bool:
    """True when orders on this account park for human approval (semi_auto)."""
    return account.mode == SEMI_AUTO or account.approval_mode == SEMI_AUTO


def park_order(
    db: Session,
    order: Order,
    *,
    parked_at: datetime | None = None,
    ttl_seconds: int = PARK_TTL_SECONDS,
    reason: str = PARK_REASON,
) -> ApprovalRequest:
    """Park one just-created order for human approval and ledger the action.

    `parked_at` is injectable so tests can prove the latency math
    deterministically; production callers use wall-clock now.
    """
    parked_at = parked_at or _utcnow()
    request = ApprovalRequest(
        user_id=order.user_id,
        order_id=order.id,
        account_id=order.account_id,
        deployment_id=order.deployment_id,
        symbol=order.symbol,
        side=order.side,
        order_type=order.order_type,
        qty=order.qty,
        limit_price=order.limit_price,
        status=ApprovalStatus.PARKED.value,
        park_reason=reason,
        parked_at=parked_at,
        expires_at=parked_at + timedelta(seconds=ttl_seconds),
    )
    db.add(request)
    db.flush()
    append_ledger(
        db,
        user_id=order.user_id,
        action="order_parked",
        subject_type="approval_request",
        subject_id=request.id,
        reason=reason,
        detail={"order_id": str(order.id), "account_id": str(order.account_id)},
    )
    db.commit()
    logger.info(
        "order_parked approval_request_id=%s order_id=%s account_id=%s symbol=%s expires_at=%s",
        request.id,
        order.id,
        order.account_id,
        order.symbol,
        request.expires_at.isoformat(),
    )
    return request


# --- read -------------------------------------------------------------------------


def get_request(db: Session, user: User, request_id) -> ApprovalRequest | None:
    """Fetch one approval request owned by the user, else None."""
    if not isinstance(request_id, UUID):
        return None
    request = db.get(ApprovalRequest, request_id)
    if request is None or request.user_id != user.id:
        return None
    return request


def list_requests(
    db: Session, user: User, status: str | None = None, order_id: UUID | None = None
) -> list[ApprovalRequest]:
    """The caller's requests, newest first, optionally filtered."""
    stmt = select(ApprovalRequest).where(ApprovalRequest.user_id == user.id)
    if status is not None:
        stmt = stmt.where(ApprovalRequest.status == status)
    if order_id is not None:
        stmt = stmt.where(ApprovalRequest.order_id == order_id)
    return list(db.scalars(stmt.order_by(ApprovalRequest.parked_at.desc())))


def broadcast_for(db: Session, request: ApprovalRequest) -> Broadcast | None:
    """The broadcast outcome row for one request, if any."""
    return db.scalar(
        select(Broadcast).where(Broadcast.approval_request_id == request.id)
    )


# --- state machine ----------------------------------------------------------------


def _transition(
    request: ApprovalRequest, target: str, *, actor_id: UUID | None, now: datetime
) -> None:
    """Apply one state-machine edge or raise 409 with a clear message."""
    legal = LEGAL_TRANSITIONS.get(request.status, set())
    if target not in legal:
        raise ApprovalError(
            409,
            f"Illegal approval transition {request.status!r} -> {target!r}; "
            f"legal transitions from {request.status!r}: "
            f"{sorted(legal) if legal else 'none (terminal)'}",
        )
    request.status = target
    request.decided_by = actor_id
    request.decided_at = now
    request.latency_ms = _latency_ms(request.parked_at, now)


def decide_request(
    db: Session,
    user: User,
    request: ApprovalRequest,
    verdict: str,
    reason: str,
    *,
    decided_at: datetime | None = None,
) -> ApprovalRequest:
    """Record the human verdict on a parked request (park -> verdict).

    Reject requires a reason (422 otherwise). The decision persists actor,
    reason, and park -> decision latency on the request and appends a ledger
    row with the same evidence. The parked order row is released to its
    verdict-mapped status; no broker call is ever made here.
    """
    if verdict not in (ApprovalStatus.APPROVED.value, ApprovalStatus.REJECTED.value):
        raise ApprovalError(422, f"Unknown verdict {verdict!r}")
    if verdict == ApprovalStatus.REJECTED.value and not reason.strip():
        raise ApprovalError(422, "A rejection requires a reason (recorded in the ledger)")
    decided_at = decided_at or _utcnow()
    _transition(
        request, verdict, actor_id=user.id, now=decided_at
    )
    request.decision_reason = reason.strip()
    order = db.get(Order, request.order_id)
    if order is not None:
        order.status = VERDICT_ORDER_STATUS[verdict]
    append_ledger(
        db,
        user_id=user.id,
        action=f"approval_{verdict}",
        subject_type="approval_request",
        subject_id=request.id,
        actor_id=user.id,
        reason=request.decision_reason,
        latency_ms=request.latency_ms,
        detail={
            "order_id": str(request.order_id),
            "symbol": request.symbol,
            "verdict": verdict,
        },
    )
    db.commit()
    logger.info(
        "approval_decided approval_request_id=%s verdict=%s actor=%s latency_ms=%s",
        request.id,
        verdict,
        user.id,
        request.latency_ms,
    )
    return request


def expire_overdue(
    db: Session, user: User, *, now: datetime | None = None
) -> list[ApprovalRequest]:
    """Sweep overdue parked requests to `expired` (the expiry path).

    Each expiry persists its park -> expiry latency and a ledger row, and
    cancels the parked order row. Idempotent: already-decided requests are
    never touched (the state machine forbids it).
    """
    now = now or _utcnow()
    overdue = list(
        db.scalars(
            select(ApprovalRequest).where(
                ApprovalRequest.user_id == user.id,
                ApprovalRequest.status == ApprovalStatus.PARKED.value,
                ApprovalRequest.expires_at < now,
            )
        )
    )
    expired: list[ApprovalRequest] = []
    for request in overdue:
        _transition(request, ApprovalStatus.EXPIRED.value, actor_id=None, now=now)
        request.decision_reason = EXPIRY_REASON
        order = db.get(Order, request.order_id)
        if order is not None:
            order.status = VERDICT_ORDER_STATUS[ApprovalStatus.EXPIRED.value]
        append_ledger(
            db,
            user_id=user.id,
            action="approval_expired",
            subject_type="approval_request",
            subject_id=request.id,
            reason=EXPIRY_REASON,
            latency_ms=request.latency_ms,
            detail={"order_id": str(request.order_id), "symbol": request.symbol},
        )
        expired.append(request)
    if expired:
        db.commit()
        logger.info(
            "approval_expiry_swept user_id=%s expired=%d", user.id, len(expired)
        )
    return expired


# --- broadcast outcomes -----------------------------------------------------------


def classify_broadcast(total: float, sent: float, queued: float) -> str:
    """Fold (total, sent, queued) into a broadcast state.

    - `sent`        — fully executed at the venue
    - `part_sent`   — partially executed, nothing queued
    - `part_queued` — partial execution with (some of) the remainder queued
    - `queued`      — nothing executed, fully queued
    """
    if sent >= total:
        return BroadcastState.SENT.value
    if sent > 0 and queued > 0:
        return BroadcastState.PART_QUEUED.value
    if sent > 0:
        return BroadcastState.PART_SENT.value
    if queued >= total:
        return BroadcastState.QUEUED.value
    return BroadcastState.PART_QUEUED.value


def report_broadcast(
    db: Session,
    user: User,
    request: ApprovalRequest,
    sent_qty: float,
    queued_qty: float,
    reason: str = "",
    *,
    created_at: datetime | None = None,
) -> Broadcast:
    """Record the venue outcome of dispatching one approved request.

    Only approved requests can report outcomes (409 otherwise). Quantities
    are validated (422): non-negative, not both zero, sum within the parked
    order quantity. The computed part-sent/part-queued state and the
    decision -> report latency land on the row and in the ledger.
    """
    if request.status != ApprovalStatus.APPROVED.value:
        raise ApprovalError(
            409,
            f"Broadcast outcomes attach to approved requests only (status is {request.status!r})",
        )
    if sent_qty < 0 or queued_qty < 0:
        raise ApprovalError(422, "sent_qty and queued_qty must be non-negative")
    if sent_qty == 0 and queued_qty == 0:
        raise ApprovalError(422, "sent_qty and queued_qty cannot both be zero")
    if sent_qty + queued_qty > request.qty + 1e-9:
        raise ApprovalError(
            422,
            f"sent_qty + queued_qty ({sent_qty + queued_qty}) exceeds order qty ({request.qty})",
        )
    existing = broadcast_for(db, request)
    if existing is not None:
        raise ApprovalError(409, "Broadcast outcome already reported for this request")

    created_at = created_at or _utcnow()
    state = classify_broadcast(request.qty, sent_qty, queued_qty)
    latency = (
        _latency_ms(request.decided_at, created_at) if request.decided_at else None
    )
    outcome_reason = (
        reason.strip()
        or f"sent {sent_qty}/{request.qty}, queued {queued_qty}/{request.qty} -> {state}"
    )
    broadcast = Broadcast(
        user_id=user.id,
        approval_request_id=request.id,
        total_qty=request.qty,
        sent_qty=sent_qty,
        queued_qty=queued_qty,
        state=state,
        reason=outcome_reason,
        latency_ms=latency,
    )
    db.add(broadcast)
    db.flush()
    append_ledger(
        db,
        user_id=user.id,
        action="broadcast_reported",
        subject_type="approval_request",
        subject_id=request.id,
        actor_id=user.id,
        reason=outcome_reason,
        latency_ms=latency,
        detail={
            "order_id": str(request.order_id),
            "state": state,
            "sent_qty": sent_qty,
            "queued_qty": queued_qty,
        },
    )
    db.commit()
    logger.info(
        "broadcast_reported approval_request_id=%s state=%s sent_qty=%s queued_qty=%s",
        request.id,
        state,
        sent_qty,
        queued_qty,
    )
    return broadcast
