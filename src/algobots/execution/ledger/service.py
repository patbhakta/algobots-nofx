"""Intent ledger service (A07): durable commit, dedup, outbox, state machine.

Spine constraint (ADR 0001): the ledger records orders and fills ONLY from
engine-derived ``OrderEvent``/``FillEvent`` contracts — the shapes a Nautilus
``ExecutionClient`` seam emits. There is no second fill path; ``demo/ledger``
is a reconciliation target, not a source. The broker fault emulator used in
tests plays the seam, never bypasses it.

Guarantees:

- Durable commit first: an intent exists in the DB before any external effect.
- Transport-key dedup: unique (tenant, idempotency_key); same key + different
  payload_hash is a conflict that leaves the original untouched (AC2).
- Active-entry guard: a partial unique index over (tenant, account,
  business_hash) for active statuses rejects repeated business signals even
  when transport keys differ.
- Exactly-once settlement: fill receipts dedup on ``FillEvent.dedup_key`` and
  cash movements are keyed to that dedup key (AC4).
- UNKNOWN is terminal-adjacent: it is entered on ambiguous delivery, exited
  only by reconciliation-origin observations; staging never mints a second
  command for the same child (AC3, "no blind resubmit").
- Ambiguous existence with no client-ID lookup freezes the account for
  conflicting entries until operator resolution (AC5).
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from algobots.contracts.events import FillEvent, OrderEvent
from algobots.contracts.outbox import ChildOrderStatusView, IntentStatusResponse, OutboxEvent
from algobots.contracts.plan import (
    ExecutionCommand,
    IntentRequest,
    OrderPlan,
    Reservation,
    canonical_hash,
)
from algobots.execution.ledger import states
from algobots.execution.ledger.errors import (
    AccountFrozen,
    AmbiguousSubmit,
    GuardRejected,
    IdempotencyConflict,
    IllegalTransitionError,
    IntentNotFound,
    LedgerError,
)
from algobots.execution.ledger.models import (
    AccountFreeze,
    CashMovement,
    ChildOrder,
    ExecutionIntent,
    FillReceipt,
    IntentOutbox,
    OrderEventReceipt,
    OrderPlanRow,
)

__all__ = [
    "CommitResult",
    "DispatchReport",
    "EventApplyResult",
    "apply_events",
    "apply_fill_event",
    "apply_order_event",
    "attach_plan",
    "business_fingerprint",
    "commit_intent",
    "dispatch_pending",
    "freeze_account",
    "get_intent",
    "mark_unknown",
    "request_cancel",
    "request_replace",
    "resolve_freeze",
    "stage_commands",
]

_EVENT_NAMESPACE = uuid.UUID("b1d30763-7a07-4f0d-a310-3a0741e07a07")  # stable: a07 outbox ids
SEP = "\x1f"


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    """SQLite DateTime columns read back naive; the ledger only writes UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _d(value: Decimal) -> str:
    return format(value, "f")


# --------------------------------------------------------------------------
# Commit (AC1 transport dedup, AC2 conflict, active-entry guard, freeze check)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CommitResult:
    intent_id: uuid.UUID
    created: bool
    status: str


def business_fingerprint(request: IntentRequest) -> str:
    """Fingerprint of the BUSINESS signal: everything except transport keys
    (idempotency_key, authority_ref) and tenant. Two intents with equal
    fingerprints are the same entry.
    """
    return canonical_hash(
        {
            "account_id": request.account_id,
            "deployment_id": request.deployment_id,
            "action": request.action.value,
            "payload": request.payload,
        }
    )


def active_freeze(db, tenant_id: uuid.UUID, account_id: str) -> AccountFreeze | None:
    return db.scalar(
        select(AccountFreeze).where(
            AccountFreeze.tenant_id == tenant_id,
            AccountFreeze.account_id == account_id,
            AccountFreeze.resolved_at.is_(None),
        )
    )


def commit_intent(
    db, tenant_id: uuid.UUID, request: IntentRequest, *, now: datetime | None = None
) -> CommitResult:
    """Durably commit an intent. Idempotent on (tenant, idempotency_key).

    Raises :class:`IdempotencyConflict` when the key exists with a different
    payload (the original row is untouched), :class:`AccountFrozen` for entry
    actions on a frozen account, :class:`GuardRejected` when an identical
    business signal is still active under different transport keys.
    """
    now = now or _utcnow()
    if request.action.value in states.ENTRY_ACTIONS:
        freeze = active_freeze(db, tenant_id, request.account_id)
        if freeze is not None:
            raise AccountFrozen(
                f"account {request.account_id} is frozen ({freeze.reason}) "
                "until operator resolution; conflicting entries are rejected"
            )
    existing = db.scalar(
        select(ExecutionIntent).where(
            ExecutionIntent.tenant_id == tenant_id,
            ExecutionIntent.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        return _existing_or_conflict(existing, request)
    row = ExecutionIntent(
        tenant_id=tenant_id,
        action=request.action.value,
        account_id=request.account_id,
        deployment_id=request.deployment_id,
        authority_ref=request.authority_ref,
        idempotency_key=request.idempotency_key,
        payload_json=_dumps(request.payload),
        payload_hash=request.payload_hash,
        business_hash=business_fingerprint(request),
        status=states.IntentState.ACCEPTED.value,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(
            select(ExecutionIntent).where(
                ExecutionIntent.tenant_id == tenant_id,
                ExecutionIntent.idempotency_key == request.idempotency_key,
            )
        )
        if existing is None:
            # The lost race was on the active-entry partial unique index.
            raise GuardRejected(
                "an identical business signal is already active for this account "
                f"({request.action.value} on {request.account_id})"
            ) from None
        return _existing_or_conflict(existing, request)
    return CommitResult(row.id, created=True, status=row.status)


def _existing_or_conflict(existing: ExecutionIntent, request: IntentRequest) -> CommitResult:
    if existing.payload_hash != request.payload_hash:
        raise IdempotencyConflict(
            f"idempotency key {request.idempotency_key!r} is bound to payload_hash "
            f"{existing.payload_hash[:12]}... (got {request.payload_hash[:12]}...); "
            "the original intent is untouched"
        )
    return CommitResult(existing.id, created=False, status=existing.status)


# --------------------------------------------------------------------------
# Plan persistence + per-account child order staging
# --------------------------------------------------------------------------


def attach_plan(
    db,
    tenant_id: uuid.UUID,
    intent_id: uuid.UUID,
    plan: OrderPlan,
    reservations: list[Reservation] | None = None,
    *,
    now: datetime | None = None,
) -> OrderPlanRow:
    """Persist an immutable plan (+ reservations). Idempotent per plan_id."""
    now = now or _utcnow()
    intent = _owned_intent(db, tenant_id, intent_id)
    existing = db.get(OrderPlanRow, plan.plan_id)
    if existing is not None:
        if existing.plan_hash != plan.plan_hash or existing.intent_id != intent.id:
            raise LedgerError(f"plan {plan.plan_id} already exists with different content")
        return existing
    row = OrderPlanRow(
        plan_id=plan.plan_id,
        intent_id=intent.id,
        account_id=plan.account_id,
        plan_hash=plan.plan_hash,
        plan_json=_dumps(plan.model_dump(mode="json")),
        reservations_json=_dumps([r.model_dump(mode="json") for r in (reservations or [])]),
        created_at=now,
    )
    db.add(row)
    if intent.status == states.IntentState.ACCEPTED.value:
        intent.status = states.IntentState.PLANNED.value
        intent.updated_at = now
    db.flush()
    return row


def client_order_id(intent_id: uuid.UUID, index: int) -> str:
    """Deterministic per-account child order ID (stable across recovery)."""
    return f"A7{intent_id.hex[:20]}C{index:03d}"


def stage_commands(
    db,
    tenant_id: uuid.UUID,
    intent_id: uuid.UUID,
    *,
    ownership_epoch: int,
    policy_revision: str,
    deadline: datetime,
    now: datetime | None = None,
) -> list[IntentOutbox]:
    """Create child orders + transactional outbox commands for every plan child.

    Idempotent: event ids are derived (uuid5) from (intent, child, epoch), so a
    replay after recovery re-derives the SAME command identity — never a
    second order for the same child (AC3's structural half).
    """
    now = now or _utcnow()
    intent = _owned_intent(db, tenant_id, intent_id)
    plan_row = db.scalar(select(OrderPlanRow).where(OrderPlanRow.intent_id == intent.id))
    if plan_row is None:
        raise LedgerError(f"intent {intent.id} has no plan to stage")
    plan = OrderPlan.model_validate(json.loads(plan_row.plan_json))
    staged: list[IntentOutbox] = []
    for index, child in enumerate(plan.children):
        cid = client_order_id(intent.id, index)
        row = db.scalar(
            select(ChildOrder).where(
                ChildOrder.intent_id == intent.id, ChildOrder.child_id == child.child_id
            )
        )
        if row is None:
            row = ChildOrder(
                tenant_id=tenant_id,
                intent_id=intent.id,
                plan_id=plan.plan_id,
                account_id=plan.account_id,
                child_id=child.child_id,
                client_order_id=cid,
                instrument_id=child.instrument_id,
                product=child.product.value,
                side=child.side.value,
                quantity_text=_d(child.quantity.value),
                limit_price_text=(
                    None if child.limit_price is None else _d(child.limit_price.amount)
                ),
                max_notional_text=_d(child.max_notional.amount),
                currency=child.max_notional.currency,
                state=states.OrderState.SUBMITTED.value,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
        elif row.state == states.OrderState.UNKNOWN.value:
            raise LedgerError(
                f"child {row.child_id} is UNKNOWN; staging a new command would be a "
                "blind resubmit — reconcile first"
            )
        event_id = uuid.uuid5(_EVENT_NAMESPACE, f"{intent.id}:{child.child_id}:{ownership_epoch}")
        outbox = db.get(IntentOutbox, event_id)
        if outbox is None:
            command = ExecutionCommand(
                schema_version=ExecutionCommand.contract_version,
                command_id=f"cmd-{event_id}",
                account_id=plan.account_id,
                ownership_epoch=ownership_epoch,
                plan_id=plan.plan_id,
                plan_hash=plan.plan_hash,
                policy_revision=policy_revision,
                deadline=deadline,
                action=plan.action,
            )
            outbox = IntentOutbox(
                event_id=event_id,
                tenant_id=tenant_id,
                intent_id=intent.id,
                plan_id=plan.plan_id,
                child_order_id=row.id,
                command_id=command.command_id,
                kind="EXECUTION_COMMAND",
                command_json=_dumps(command.model_dump(mode="json")),
                emitted_at=now,
                created_at=now,
            )
            db.add(outbox)
            staged.append(outbox)
    intent.status = states.IntentState.SUBMITTED.value
    intent.updated_at = now
    db.flush()
    return staged


# --------------------------------------------------------------------------
# Outbox dispatch + UNKNOWN/freeze handling
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DispatchReport:
    delivered: int
    ambiguous: int
    attempted: int


def dispatch_pending(
    db,
    sink,
    *,
    tenant_id: uuid.UUID | None = None,
    now: datetime | None = None,
    limit: int | None = None,
) -> DispatchReport:
    """Drain PENDING outbox rows to ``sink`` (the execution seam).

    ``tenant_id`` scopes the drain (None = every tenant, the worker default).

    On :class:`AmbiguousSubmit` the child order goes UNKNOWN — and the account
    is frozen when the broker cannot answer a client-ID lookup — while the
    row STAYS PENDING: recovery replay re-delivers the very same event id and
    command, which the seam deduplicates. A replay is not a resubmit.
    """
    now = now or _utcnow()
    query = (
        select(IntentOutbox)
        .where(IntentOutbox.status == "PENDING")
        .order_by(IntentOutbox.created_at, IntentOutbox.event_id)
    )
    if tenant_id is not None:
        query = query.where(IntentOutbox.tenant_id == tenant_id)
    if limit is not None:
        query = query.limit(limit)
    rows = list(db.scalars(query))
    delivered = ambiguous = 0
    for row in rows:
        row.attempts += 1
        try:
            sink(wire_event(row))
        except AmbiguousSubmit as exc:
            ambiguous += 1
            row.last_error = exc.reason
            _mark_unknown(
                db,
                row.tenant_id,
                row.child_order_id,
                reason=exc.reason,
                lookup_available=exc.lookup_available,
                now=now,
            )
            continue
        except Exception as exc:  # transient seam failure: retry on next drain
            row.last_error = f"{type(exc).__name__}: {exc}"
            continue
        row.status = "DISPATCHED"
        row.dispatched_at = now
        row.last_error = None
        delivered += 1
    db.flush()
    return DispatchReport(delivered=delivered, ambiguous=ambiguous, attempted=len(rows))


# Kept as an explicit alias because the packet speaks of "replaying the outbox
# using stable identities after recovery".
replay_outbox = dispatch_pending


def wire_event(row: IntentOutbox) -> OutboxEvent:
    command = ExecutionCommand.model_validate(json.loads(row.command_json))
    return OutboxEvent(
        schema_version=OutboxEvent.contract_version,
        event_id=str(row.event_id),
        tenant_id=str(row.tenant_id),
        intent_id=str(row.intent_id),
        plan_id=row.plan_id,
        command=command,
        emitted_at=_aware(row.emitted_at),
    )


def mark_unknown(
    db,
    tenant_id: uuid.UUID,
    child_order_id: uuid.UUID,
    reason: str,
    *,
    lookup_available: bool = True,
    now: datetime | None = None,
) -> ChildOrder:
    return _mark_unknown(
        db, tenant_id, child_order_id, reason=reason, lookup_available=lookup_available, now=now
    )


def _mark_unknown(
    db,
    tenant_id: uuid.UUID,
    child_order_id: uuid.UUID,
    *,
    reason: str,
    lookup_available: bool,
    now: datetime | None = None,
) -> ChildOrder:
    now = now or _utcnow()
    child = _owned_child(db, tenant_id, child_order_id)
    try:
        child.state = states.transition(states.OrderState(child.state), states.OrderState.UNKNOWN)
    except states.IllegalTransition as exc:
        raise IllegalTransitionError(str(exc)) from exc
    child.updated_at = now
    _refresh_intent(db, child.intent_id, now=now)
    if not lookup_available:
        freeze_account(
            db,
            tenant_id,
            child.account_id,
            reason="AMBIGUOUS_EXISTENCE",
            detail={"child_order_id": str(child.id), "reason": reason},
            now=now,
        )
    return child


def freeze_account(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    *,
    reason: str,
    detail: dict | None = None,
    now: datetime | None = None,
) -> AccountFreeze:
    """Freeze an account (idempotent: one ACTIVE freeze per account)."""
    now = now or _utcnow()
    existing = active_freeze(db, tenant_id, account_id)
    if existing is not None:
        return existing
    row = AccountFreeze(
        tenant_id=tenant_id,
        account_id=account_id,
        reason=reason,
        detail_json=_dumps(detail or {}),
        created_at=now,
    )
    nested = db.begin_nested()  # savepoint: a lost race must not undo the caller's txn
    db.add(row)
    try:
        nested.commit()
    except IntegrityError:
        nested.rollback()
        existing = active_freeze(db, tenant_id, account_id)
        assert existing is not None
        return existing
    return row


def resolve_freeze(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    *,
    resolved_by: str,
    note: str,
    now: datetime | None = None,
) -> AccountFreeze:
    """Operator resolution: close the active freeze (AC5's unblock path)."""
    now = now or _utcnow()
    row = active_freeze(db, tenant_id, account_id)
    if row is None:
        raise LedgerError(f"account {account_id} has no active freeze to resolve")
    row.resolved_at = now
    row.resolved_by = resolved_by
    row.resolution_note = note
    db.flush()
    return row


# --------------------------------------------------------------------------
# Event application (dedup, mapping, state machine, settlement, projections)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class EventApplyResult:
    applied: bool
    reason: str = ""


def apply_order_event(
    db, tenant_id: uuid.UUID, event: OrderEvent, *, now: datetime | None = None
) -> EventApplyResult:
    """Record one OrderEvent: dedup, learn broker/client mapping, transition."""
    now = now or _utcnow()
    dedup = SEP.join(
        (str(tenant_id), event.environment.value, event.account_id, event.event_id, event.status)
    )
    if db.scalar(select(OrderEventReceipt).where(OrderEventReceipt.dedup_key == dedup)):
        return EventApplyResult(False, "duplicate")
    child = db.scalar(
        select(ChildOrder).where(
            ChildOrder.tenant_id == tenant_id,
            ChildOrder.account_id == event.account_id,
            ChildOrder.client_order_id == event.client_order_id,
        )
    )
    if child is None:
        return EventApplyResult(False, "unknown_client_order")
    if event.broker_order_id and child.broker_order_id is None:
        child.broker_order_id = event.broker_order_id
    elif event.broker_order_id and child.broker_order_id != event.broker_order_id:
        raise LedgerError(
            f"client order {child.client_order_id} remapped from "
            f"{child.broker_order_id} to {event.broker_order_id}; refusing"
        )
    target = states.EVENT_STATUS_TO_STATE[event.status]
    try:
        child.state = states.transition(
            states.OrderState(child.state), target, reconciliation=event.reconciliation_origin
        )
    except states.IllegalTransition as exc:
        raise IllegalTransitionError(
            f"client order {child.client_order_id}: {exc}"
        ) from exc
    child.updated_at = now
    db.add(
        OrderEventReceipt(
            dedup_key=dedup,
            child_order_id=child.id,
            event_id=event.event_id,
            status=event.status,
            reconciliation_origin=event.reconciliation_origin,
            event_json=_dumps(event.model_dump(mode="json")),
            event_time=event.event_time,
            received_time=event.received_time,
            recorded_at=now,
        )
    )
    _refresh_intent(db, child.intent_id, now=now)
    db.flush()
    return EventApplyResult(True)


def apply_fill_event(
    db, tenant_id: uuid.UUID, event: FillEvent, *, now: datetime | None = None
) -> EventApplyResult:
    """Record one FillEvent exactly once: receipt, cash settlement, projection.

    A duplicate delivery is a no-op (AC4). A fill whose broker order is not
    yet mapped defers (``applied=False, reason="unmapped"``) so a reordered
    batch can be pumped to a fixpoint by :func:`apply_events`.
    """
    now = now or _utcnow()
    dedup = SEP.join((str(tenant_id), *event.dedup_key))
    if db.scalar(select(FillReceipt).where(FillReceipt.dedup_key == dedup)):
        return EventApplyResult(False, "duplicate")
    child = db.scalar(
        select(ChildOrder).where(
            ChildOrder.tenant_id == tenant_id,
            ChildOrder.account_id == event.account_id,
            ChildOrder.broker_order_id == event.broker_order_id,
        )
    )
    if child is None:
        return EventApplyResult(False, "unmapped")
    qty, px, fee = event.quantity.value, event.price.amount, event.fee.amount
    signed = qty * px if event.side.value == "SELL" else -(qty * px)
    for kind, amount in (("FILL_NOTIONAL", signed), ("FEE", -fee)):
        db.add(
            CashMovement(
                movement_key=f"fill:{dedup}:{kind.lower()}",
                tenant_id=tenant_id,
                account_id=event.account_id,
                kind=kind,
                amount_text=_d(amount),
                currency=event.price.currency,
                ref_type="fill",
                ref_id=event.fill_id,
                created_at=now,
            )
        )
    old_qty, old_avg = child.filled_qty, child.avg_px_text
    new_filled = old_qty + qty
    if new_filled > child.quantity:
        raise LedgerError(
            f"fill {event.fill_id} overfills client order {child.client_order_id}: "
            f"{new_filled} > {child.quantity}"
        )
    child.filled_qty_text = _d(new_filled)
    prior_notional = (Decimal(old_avg) * old_qty) if old_avg else Decimal(0)
    child.avg_px_text = _d((prior_notional + qty * px) / new_filled) if new_filled else None
    child.fees_text = _d(child.fees + fee)
    target = (
        states.OrderState.FILLED
        if new_filled >= child.quantity
        else states.OrderState.PARTIALLY_FILLED
    )
    try:
        child.state = states.transition(
            states.OrderState(child.state), target, reconciliation=event.reconciliation_origin
        )
    except states.IllegalTransition as exc:
        raise IllegalTransitionError(f"client order {child.client_order_id}: {exc}") from exc
    child.updated_at = now
    db.add(
        FillReceipt(
            dedup_key=dedup,
            child_order_id=child.id,
            fill_id=event.fill_id,
            account_id=event.account_id,
            instrument_id=event.instrument_id,
            side=event.side.value,
            quantity_text=_d(qty),
            price_text=_d(px),
            fee_text=_d(fee),
            currency=event.price.currency,
            corrects_fill_id=event.corrects_fill_id,
            event_time=event.event_time,
            received_time=event.received_time,
            recorded_at=now,
        )
    )
    _refresh_intent(db, child.intent_id, now=now)
    db.flush()
    return EventApplyResult(True)


def apply_events(
    db, tenant_id: uuid.UUID, events: list[OrderEvent | FillEvent], *, now: datetime | None = None
) -> list[EventApplyResult]:
    """Apply a batch tolerating reordering: fills that arrive before their
    order-acknowledgment are deferred and retried once the mapping event in
    the same batch has landed (AC4's "delivered out of order"). Each event
    reports its FINAL disposition (a deferred-then-applied fill reports
    ``applied=True``).
    """
    outcomes: dict[int, EventApplyResult] = {}
    pending = list(enumerate(events))
    progress = True
    while pending and progress:
        progress = False
        deferred: list[tuple[int, OrderEvent | FillEvent]] = []
        for index, event in pending:
            if isinstance(event, FillEvent):
                result = apply_fill_event(db, tenant_id, event, now=now)
            else:
                result = apply_order_event(db, tenant_id, event, now=now)
            if result.reason == "unmapped":
                deferred.append((index, event))
            else:
                outcomes[index] = result
                progress = progress or result.applied
        pending = deferred
    for index, _ in pending:
        outcomes[index] = EventApplyResult(False, "unmapped")
    return [outcomes[i] for i in range(len(events))]


def request_cancel(
    db, tenant_id: uuid.UUID, child_order_id: uuid.UUID, *, now: datetime | None = None
) -> ChildOrder:
    return _request_pending(
        db, tenant_id, child_order_id, states.OrderState.PENDING_CANCEL, now=now
    )


def request_replace(
    db, tenant_id: uuid.UUID, child_order_id: uuid.UUID, *, now: datetime | None = None
) -> ChildOrder:
    return _request_pending(
        db, tenant_id, child_order_id, states.OrderState.PENDING_REPLACE, now=now
    )


def _request_pending(
    db, tenant_id: uuid.UUID, child_order_id: uuid.UUID, target: states.OrderState, *, now=None
) -> ChildOrder:
    now = now or _utcnow()
    child = _owned_child(db, tenant_id, child_order_id)
    try:
        child.state = states.transition(states.OrderState(child.state), target)
    except states.IllegalTransition as exc:
        raise IllegalTransitionError(str(exc)) from exc
    child.updated_at = now
    _refresh_intent(db, child.intent_id, now=now)
    db.flush()
    return child


# --------------------------------------------------------------------------
# Status view (/intents/{id} response)
# --------------------------------------------------------------------------


def get_intent(db, tenant_id: uuid.UUID, intent_id: uuid.UUID) -> IntentStatusResponse:
    intent = _owned_intent(db, tenant_id, intent_id)
    children = list(db.scalars(select(ChildOrder).where(ChildOrder.intent_id == intent.id)))
    orders = tuple(
        ChildOrderStatusView(
            schema_version=ChildOrderStatusView.contract_version,
            child_id=c.child_id,
            client_order_id=c.client_order_id,
            broker_order_id=c.broker_order_id,
            instrument_id=c.instrument_id,
            side=c.side,
            state=c.state,
            quantity=c.quantity_text,
            filled_quantity=c.filled_qty_text,
            average_fill_price=c.avg_px_text,
            accrued_fees=c.fees_text,
            currency=c.currency,
        )
        for c in sorted(children, key=lambda c: c.child_id)
    )
    plan_id = db.scalar(select(OrderPlanRow.plan_id).where(OrderPlanRow.intent_id == intent.id))
    return IntentStatusResponse(
        schema_version=IntentStatusResponse.contract_version,
        intent_id=str(intent.id),
        idempotency_key=intent.idempotency_key,
        action=intent.action,
        account_id=intent.account_id,
        payload_hash=intent.payload_hash,
        status=intent.status,
        plan_id=plan_id,
        orders=orders,
        account_frozen=active_freeze(db, tenant_id, intent.account_id) is not None,
        created_at=_aware(intent.created_at),
        updated_at=_aware(intent.updated_at),
    )


# --------------------------------------------------------------------------
# internals
# --------------------------------------------------------------------------


def _owned_intent(db, tenant_id: uuid.UUID, intent_id: uuid.UUID) -> ExecutionIntent:
    intent = db.get(ExecutionIntent, intent_id)
    if intent is None or intent.tenant_id != tenant_id:
        raise IntentNotFound(f"intent {intent_id} does not exist for this tenant")
    return intent


def _owned_child(db, tenant_id: uuid.UUID, child_order_id: uuid.UUID) -> ChildOrder:
    child = db.get(ChildOrder, child_order_id)
    if child is None or child.tenant_id != tenant_id:
        raise IntentNotFound(f"child order {child_order_id} does not exist for this tenant")
    return child


def _refresh_intent(db, intent_id: uuid.UUID, *, now: datetime | None = None) -> None:
    now = now or _utcnow()
    intent = db.get(ExecutionIntent, intent_id)
    if intent is None:
        return
    child_states = [
        states.OrderState(s)
        for (s,) in db.execute(select(ChildOrder.state).where(ChildOrder.intent_id == intent_id))
    ]
    planned = (
        db.scalar(select(OrderPlanRow.plan_id).where(OrderPlanRow.intent_id == intent_id))
        is not None
    )
    status = states.intent_rollup(child_states, planned=planned)
    if intent.status != status.value:
        intent.status = status.value
        intent.updated_at = now
