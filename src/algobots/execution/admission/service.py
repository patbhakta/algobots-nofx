"""Account admission serialization + reservation lifecycle (A08).

The single place a proposal becomes a committed, funded dispatch intent:

1. evaluate the frozen policy (``risk.policy``) — deterministic decision;
2. check live operator controls (``risk.controls``);
3. serialize at the account row with ONE guarded ``UPDATE`` whose WHERE
   clause is the overcommit invariant — two simultaneous $700 entries on a
   $1,000 pool cannot both win (AC1), whatever the interleaving;
4. persist the dispatch intent through the A07 ledger (``commit_intent`` →
   ``attach_plan`` with the reservation contracts) IN THE SAME TRANSACTION,
   so a funded reservation without an intent — or an intent without funds —
   cannot exist;
5. lifecycle: release/resize ONLY on reconciled rejection, cancellation,
   fill, expiry or explicit operator correction; UNKNOWN and cancel-pending
   retain their obligations (AC2) as ``UNCERTAIN``.

Fail-closed law: any error between the guarded UPDATE and the commit rolls
the whole transaction back — a risk-store failure never leaves new exposure
admitted, and never strands a reservation without its intent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from algobots.contracts.plan import IntentRequest, OrderPlan, Reservation
from algobots.contracts.risk import RiskDecision, RiskPolicyVersion
from algobots.execution.admission.errors import (
    AdmissionDenied,
    AdmissionError,
    OvercommitRejected,
    ReservationNotFound,
)
from algobots.execution.admission.models import (
    ACTIVE_RESERVATION_STATES,
    AccountAdmission,
    AccountControlRow,
    AccountInventory,
    InstrumentMarkRow,
    ReservationRow,
)
from algobots.execution.ledger import attach_plan, commit_intent
from algobots.risk.controls import AccountControls, ControlAction, check_action
from algobots.risk.policy import (
    AccountRiskState,
    InstrumentMark,
    RiskProposal,
    buffered_reservation,
    evaluate_proposal,
)

__all__ = [
    "AdmissionResult",
    "admit_entry",
    "available_cash",
    "consume_on_fill",
    "deposit",
    "expire_reservations",
    "get_controls",
    "get_or_create_admission",
    "mark_uncertain",
    "record_mark",
    "release_reservation",
    "resize_reservation",
    "set_controls",
    "set_inventory",
    "state_snapshot",
]


#: Bounded attempts for every compare-and-swap on an account pool row.
_CAS_ATTEMPTS = 8


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _d(value: Decimal) -> str:
    return format(value, "f")


# --------------------------------------------------------------------------
# Account pool + state snapshot
# --------------------------------------------------------------------------


def get_or_create_admission(
    db, tenant_id: uuid.UUID, account_id: str, *, cash: Decimal, currency: str = "USD"
) -> AccountAdmission:
    row = db.get(AccountAdmission, (tenant_id, account_id))
    if row is not None:
        return row
    row = AccountAdmission(
        tenant_id=tenant_id,
        account_id=account_id,
        currency=currency,
        cash_available_text=_d(cash),
        cash_reserved_text="0",
    )
    db.add(row)
    db.flush()
    return row


def deposit(
    db, tenant_id: uuid.UUID, account_id: str, amount: Decimal, *, now: datetime | None = None
) -> AccountAdmission:
    """Record a deposit/withdrawal on the pool (sign carries direction).

    Review finding F1 (ALG-3306): the pool row's ``version`` epoch is the
    admission CAS's serialization token, so deposits take the SAME CAS
    discipline — a plain ORM write-back could regress the epoch when
    interleaved with concurrent admissions on Postgres. A deposit never
    touches the reserved counter, so this is epoch hygiene, not a funds
    invariant; the withdrawal side additionally refuses to strand active
    reservations below their claims.
    """
    now = now or _utcnow()
    for _ in range(_CAS_ATTEMPTS):
        row = db.get(AccountAdmission, (tenant_id, account_id))
        if row is None:
            raise ReservationNotFound(f"account {account_id} has no admission row")
        new_available = row.cash_available + amount
        if new_available < row.cash_reserved:
            raise AdmissionError(
                f"withdrawal {amount} would strand active reservations "
                f"({row.cash_reserved} claimed > {new_available} available)"
            )
        seen_version = row.version
        try:
            result = db.execute(
                update(AccountAdmission)
                .where(
                    AccountAdmission.tenant_id == tenant_id,
                    AccountAdmission.account_id == account_id,
                    AccountAdmission.version == seen_version,
                )
                .values(
                    cash_available_text=_d(new_available),
                    version=seen_version + 1,
                    updated_at=now,
                )
            )
        except OperationalError:
            try:
                db.rollback()
            except OperationalError:
                pass
            continue
        if result.rowcount == 1:
            db.flush()
            return db.get(AccountAdmission, (tenant_id, account_id))
        try:
            db.rollback()
        except OperationalError:
            pass
    db.rollback()
    raise AdmissionError(
        f"deposit for account {account_id} did not converge in {_CAS_ATTEMPTS} attempts"
    )


def set_inventory(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    instrument_id: str,
    held: Decimal,
    unit: str = "contracts",
    *,
    now: datetime | None = None,
) -> AccountInventory:
    now = now or _utcnow()
    row = db.get(AccountInventory, (tenant_id, account_id, instrument_id))
    if row is None:
        row = AccountInventory(
            tenant_id=tenant_id,
            account_id=account_id,
            instrument_id=instrument_id,
            unit=unit,
            held_text=_d(held),
            reserved_text="0",
            updated_at=now,
        )
        db.add(row)
    else:
        row.held_text = _d(held)
        row.updated_at = now
    db.flush()
    return row


def record_mark(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    instrument_id: str,
    *,
    price: Decimal,
    currency: str,
    quality: str,
    observed_at: datetime,
) -> InstrumentMarkRow:
    row = db.get(InstrumentMarkRow, (tenant_id, account_id, instrument_id))
    if row is None:
        row = InstrumentMarkRow(
            tenant_id=tenant_id,
            account_id=account_id,
            instrument_id=instrument_id,
            price_text=_d(price),
            currency=currency,
            quality=quality,
            observed_at=observed_at,
        )
        db.add(row)
    else:
        row.price_text = _d(price)
        row.currency = currency
        row.quality = quality
        row.observed_at = observed_at
    db.flush()
    return row


def available_cash(db, tenant_id: uuid.UUID, account_id: str) -> Decimal:
    row = db.get(AccountAdmission, (tenant_id, account_id))
    if row is None:
        raise ReservationNotFound(f"account {account_id} has no admission row")
    return row.cash_available - row.cash_reserved


def state_snapshot(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    instrument_id: str,
    *,
    equity_reference: Decimal,
    gross_exposure: Decimal = Decimal(0),
    instrument_exposure: Decimal = Decimal(0),
    instrument_position: Decimal = Decimal(0),
    deployment_gross_notional: Decimal = Decimal(0),
    daily_pnl: Decimal = Decimal(0),
    connected: bool = True,
    reconciled_within_seconds: int | None = None,
) -> AccountRiskState:
    """Build the policy's state snapshot from the admission store — funds
    figures are net of ACTIVE reservations (HELD + UNCERTAIN)."""
    row = db.get(AccountAdmission, (tenant_id, account_id))
    if row is None:
        raise ReservationNotFound(f"account {account_id} has no admission row")
    mark_row = db.get(InstrumentMarkRow, (tenant_id, account_id, instrument_id))
    mark = None
    if mark_row is not None:
        mark = InstrumentMark(
            instrument_id=mark_row.instrument_id,
            price=mark_row.price,
            quality=mark_row.quality,  # type: ignore[arg-type]
            observed_at=_aware(mark_row.observed_at),
        )
    return AccountRiskState(
        cash_available=row.cash_available,
        cash_reserved=row.cash_reserved,
        gross_exposure=gross_exposure,
        equity_reference=equity_reference,
        instrument_exposure=instrument_exposure,
        instrument_position=instrument_position,
        instrument_mark=mark,
        deployment_gross_notional=deployment_gross_notional,
        daily_pnl=daily_pnl,
        connected=connected,
        reconciled_within_seconds=reconciled_within_seconds,
    )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# --------------------------------------------------------------------------
# Controls persistence
# --------------------------------------------------------------------------


def get_controls(db, tenant_id: uuid.UUID, account_id: str) -> AccountControls:
    row = db.get(AccountControlRow, (tenant_id, account_id))
    if row is None:
        return AccountControls()
    return AccountControls(
        entries_paused=row.entries_paused,
        cancel_entries_requested=row.cancel_entries_requested,
        reduce_only=row.reduce_only,
        flatten_authorized_by=row.flatten_authorized_by,
        flatten_authorized_at=(
            None if row.flatten_authorized_at is None else _aware(row.flatten_authorized_at)
        ),
        flatten_valid_until=(
            None if row.flatten_valid_until is None else _aware(row.flatten_valid_until)
        ),
        updated_at=None if row.updated_at is None else _aware(row.updated_at),
    )


def set_controls(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    controls: AccountControls,
    *,
    now: datetime | None = None,
) -> AccountControls:
    now = now or _utcnow()
    row = db.get(AccountControlRow, (tenant_id, account_id))
    if row is None:
        row = AccountControlRow(tenant_id=tenant_id, account_id=account_id, updated_at=now)
        db.add(row)
    row.entries_paused = controls.entries_paused
    row.cancel_entries_requested = controls.cancel_entries_requested
    row.reduce_only = controls.reduce_only
    row.flatten_authorized_by = controls.flatten_authorized_by
    row.flatten_authorized_at = controls.flatten_authorized_at
    row.flatten_valid_until = controls.flatten_valid_until
    row.updated_at = now
    db.flush()
    return get_controls(db, tenant_id, account_id)


# --------------------------------------------------------------------------
# Admission (the serialized point)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdmissionResult:
    decision: RiskDecision
    intent_id: uuid.UUID
    plan_id: str
    reservations: tuple[Reservation, ...]
    reserved: Decimal  # funds claim taken (amount + buffers)


def admit_entry(
    db,
    tenant_id: uuid.UUID,
    policy: RiskPolicyVersion,
    proposal: RiskProposal,
    request: IntentRequest,
    plan: OrderPlan,
    *,
    state: AccountRiskState | None = None,
    now: datetime | None = None,
) -> AdmissionResult:
    """Policy → controls → reservations → ledger commit, one transaction.

    Raises :class:`AdmissionDenied` (policy/controls), :class:`OvercommitRejected`
    (lost the funds race or insufficient unreserved cash), or rolls everything
    back on any store failure — a reservation can never outlive its intent.
    """
    now = now or _utcnow()
    if plan.account_id != proposal.account_id or request.account_id != proposal.account_id:
        raise AdmissionError("proposal, request and plan must name the same account")

    snapshot = state
    if snapshot is None:
        snapshot = state_snapshot(
            db, tenant_id, proposal.account_id, proposal.instrument_id,
            equity_reference=proposal.reference_price * proposal.quantity,
        )

    # 1. policy — deterministic, auditable
    decision = evaluate_proposal(policy, proposal, snapshot, now=now)
    if decision.decision == "DENY":
        raise AdmissionDenied(decision)

    # 2. live controls — operator state, not policy
    action = {
        "ENTRY": ControlAction.ENTRY,
        "EXIT": ControlAction.EXIT,
        "REDUCE": ControlAction.REDUCE,
        "PROTECTIVE": ControlAction.PROTECTIVE,
    }[proposal.kind]

    notional = (
        decision.approved_notional.amount
        if decision.approved_notional
        else proposal.notional
    )

    # 3. reservations: one CASH row per plan child (principal + buffers).
    #    The pool claim is EXACTLY the sum of row claims — the invariant
    #    sum(active reservations) == pool reserved holds by construction.
    #    A clamped plan is stale: admission fails closed with an explicit
    #    error; the strategy re-plans at the clamped size.
    #    Review finding F2 (ALG-3306): each row claim quantizes principal and
    #    buffer separately (<= one cent of drift per row) while the policy's
    #    required_reservation quantizes the whole notional once — a multi-
    #    child plan at the exact boundary could be spuriously rejected by
    #    sub-cent drift. The comparison therefore tolerates one cent per
    #    reservation row; anything beyond that is still a stale plan.
    reservations = _plan_reservations(policy, plan, now=now)
    required = sum(
        _reservation_amount(r) + _reservation_buffer(r) for r in reservations
    )
    policy_required = (
        decision.required_reservation.amount
        if decision.required_reservation
        else buffered_reservation(policy, notional)
    )
    tolerance = Decimal("0.01") * len(reservations)
    if required > policy_required + tolerance:
        db.rollback()
        raise AdmissionError(
            f"plan reservation claim {required} exceeds the policy-approved "
            f"reservation {policy_required} (decision: {decision.decision}"
            f"{f' [{decision.rule}]' if decision.rule else ''}); re-plan at the "
            "approved size"
        )

    # 4. serialize: controls check + compare-and-swap on the account row's
    #    ``version`` epoch. The funds invariant (reserved + required <=
    #    available) is checked in exact Decimal arithmetic against the row the
    #    CAS read; the CAS fails if any concurrent admission moved the row
    #    first. Two simultaneous $700 entries on a $1,000 pool: one CAS wins,
    #    the loser re-reads the committed reserved counter and is rejected
    #    (AC1) — on any engine. Controls are re-checked on every retry so a
    #    pause that landed mid-race is honored.
    _controls_and_reserve(db, tenant_id, proposal.account_id, action, required, policy)

    for reservation in reservations:
        db.add(
            ReservationRow(
                reservation_id=reservation.reservation_id,
                tenant_id=tenant_id,
                account_id=reservation.account_id,
                plan_id=reservation.plan_id,
                child_id=reservation.child_id,
                kind=reservation.kind,
                instrument_id=reservation.instrument_id,
                unit=_reservation_unit(reservation),
                amount_text=_d(_reservation_amount(reservation)),
                buffer_text=_d(_reservation_buffer(reservation)),
                state="HELD",
                created_at=now,
                updated_at=now,
            )
        )
    try:
        commit = commit_intent(db, tenant_id, request, now=now)
        attach_plan(db, tenant_id, commit.intent_id, plan, list(reservations), now=now)
    except SQLAlchemyError:
        # fail closed: no reservation may outlive its intent
        db.rollback()
        raise
    db.flush()
    return AdmissionResult(
        decision=decision,
        intent_id=commit.intent_id,
        plan_id=plan.plan_id,
        reservations=tuple(reservations),
        reserved=required,
    )


def _controls_and_reserve(
    db,
    tenant_id: uuid.UUID,
    account_id: str,
    action: ControlAction,
    required: Decimal,
    policy: RiskPolicyVersion,
) -> None:
    """Controls check + bounded CAS loop: reserve ``required`` against the
    account pool or raise (:class:`AdmissionDenied` / :class:`OvercommitRejected`).
    Exact Decimal math, no SQL arithmetic on money text columns. Every retry
    re-checks controls so an operator pause that landed mid-race is honored."""
    from sqlalchemy.exc import OperationalError

    for _ in range(_CAS_ATTEMPTS):
        check = check_action(get_controls(db, tenant_id, account_id), action)
        if not check.allowed:
            raise AdmissionDenied(
                RiskDecision(
                    schema_version="1.0",
                    decision="DENY",
                    rule="account_control",
                    reason=check.reason,
                    policy_revision=policy.policy_revision,
                )
            )
        account = db.get(AccountAdmission, (tenant_id, account_id))
        if account is None:
            raise ReservationNotFound(
                f"account {account_id} has no admission row; refusing to admit"
            )
        unreserved = account.cash_available - account.cash_reserved
        if required > unreserved:
            raise OvercommitRejected(required, unreserved)
        seen_version = account.version
        new_reserved = account.cash_reserved + required
        try:
            result = db.execute(
                update(AccountAdmission)
                .where(
                    AccountAdmission.tenant_id == tenant_id,
                    AccountAdmission.account_id == account_id,
                    AccountAdmission.version == seen_version,
                )
                .values(
                    cash_reserved_text=_d(new_reserved),
                    version=seen_version + 1,
                    updated_at=_utcnow(),
                )
            )
        except OperationalError:
            # SQLite WAL snapshot-upgrade contention: start a fresh snapshot.
            try:
                db.rollback()
            except OperationalError:
                pass
            continue
        if result.rowcount == 1:
            return
        # lost the CAS: a concurrent admission moved the row. Re-read under a
        # fresh snapshot (SQLite WAL upgrade contention surfaces as busy).
        try:
            db.rollback()
        except OperationalError:
            pass
    db.rollback()
    raise AdmissionError(
        f"admission serialization for account {account_id} did not converge "
        f"in {_CAS_ATTEMPTS} attempts"
    )


def _reservation_unit(reservation: Reservation) -> str:
    amount = reservation.amount
    return amount.currency if hasattr(amount, "currency") else amount.unit


def _reservation_amount(reservation: Reservation) -> Decimal:
    amount = reservation.amount
    return amount.amount if hasattr(amount, "currency") else amount.value


def _reservation_buffer(reservation: Reservation) -> Decimal:
    buffer = reservation.buffer
    return buffer.amount if hasattr(buffer, "currency") else buffer.value


def _plan_reservations(
    policy: RiskPolicyVersion, plan: OrderPlan, *, now: datetime
) -> list[Reservation]:
    """One CASH reservation per plan child: principal + fee/slippage buffer.

    The buffers come from the policy's buffer bps over the child notional —
    the same headroom the policy's ``required_reservation`` computed, so the
    sum of row claims equals the pool claim taken by admission.
    """
    c = policy.constraints
    bps = c.fee_buffer_bps + c.slippage_buffer_bps
    reservations: list[Reservation] = []
    for child in plan.children:
        child_notional = child.quantity.value * (
            child.limit_price.amount if child.limit_price else child.max_notional.amount
        )
        principal = child_notional.quantize(Decimal("0.01"))
        buffer = (child_notional * bps / Decimal(10000)).quantize(Decimal("0.01"))
        reservations.append(
            Reservation(
                schema_version="1.0",
                reservation_id=f"resv-{plan.plan_id}-{child.child_id}",
                account_id=plan.account_id,
                instrument_id=child.instrument_id,
                plan_id=plan.plan_id,
                child_id=child.child_id,
                kind="CASH",
                amount={"amount": _d(principal), "currency": child.max_notional.currency},
                buffer={"amount": _d(buffer), "currency": child.max_notional.currency},
                state="HELD",
                version=0,
            )
        )
    return reservations


# --------------------------------------------------------------------------
# Reservation lifecycle: release / resize / uncertain / expiry
# --------------------------------------------------------------------------


_RELEASE_REASONS = frozenset(
    {"RECONCILED_REJECTION", "CANCELED", "FILLED", "EXPIRED", "OPERATOR_CORRECTION"}
)


def release_reservation(
    db,
    tenant_id: uuid.UUID,
    reservation_id: str,
    reason: str,
    *,
    now: datetime | None = None,
) -> ReservationRow:
    """Release an active reservation back to the pool. Only reconciled
    rejection, cancellation, fill, expiry or an explicit operator correction
    may release — the reason is recorded on the row."""
    now = now or _utcnow()
    if reason not in _RELEASE_REASONS:
        raise AdmissionError(
            f"release reason {reason!r} is not one of {sorted(_RELEASE_REASONS)}"
        )
    row = _active(db, tenant_id, reservation_id)
    claim = row.claim
    row.state = "RELEASED"
    row.released_at = now
    row.release_reason = reason
    row.version += 1
    row.updated_at = now
    _adjust_pool(db, tenant_id, row.account_id, -claim, now)
    db.flush()
    return row


def consume_on_fill(
    db,
    tenant_id: uuid.UUID,
    reservation_id: str,
    *,
    settle_amount: Decimal,
    now: datetime | None = None,
) -> ReservationRow:
    """A fill settles: the reservation is CONSUMED, the pool is charged the
    settled cash (notional + fees) and the unused buffer returns."""
    now = now or _utcnow()
    row = _active(db, tenant_id, reservation_id)
    claim = row.claim
    row.state = "CONSUMED"
    row.released_at = now
    row.release_reason = "FILLED"
    row.version += 1
    row.updated_at = now
    account = db.get(AccountAdmission, (tenant_id, row.account_id))
    if account is None:
        raise ReservationNotFound(f"account {row.account_id} has no admission row")
    account.cash_available_text = _d(account.cash_available - settle_amount)
    account.cash_reserved_text = _d(account.cash_reserved - claim)
    account.version += 1
    account.updated_at = now
    db.flush()
    return row


def resize_reservation(
    db,
    tenant_id: uuid.UUID,
    reservation_id: str,
    *,
    new_amount: Decimal,
    new_buffer: Decimal | None = None,
    reason: str = "OPERATOR_CORRECTION",
    now: datetime | None = None,
) -> ReservationRow:
    """Resize an active reservation (explicit operator correction, or a
    partial-fill remainder). The pool counter follows the delta."""
    now = now or _utcnow()
    if reason not in {"OPERATOR_CORRECTION", "PARTIAL_FILL"}:
        raise AdmissionError("resize reason must be OPERATOR_CORRECTION or PARTIAL_FILL")
    row = _active(db, tenant_id, reservation_id)
    old_claim = row.claim
    buffer = row.buffer if new_buffer is None else new_buffer
    if new_amount <= 0 or buffer < 0:
        raise AdmissionError("resized amount must be > 0 and buffer >= 0")
    row.amount_text = _d(new_amount)
    row.buffer_text = _d(buffer)
    row.version += 1
    row.updated_at = now
    _adjust_pool(db, tenant_id, row.account_id, row.claim - old_claim, now)
    db.flush()
    return row


def mark_uncertain(
    db,
    tenant_id: uuid.UUID,
    reservation_id: str,
    *,
    now: datetime | None = None,
) -> ReservationRow:
    """UNKNOWN order or cancel-pending: the obligation RETAINS its claim
    (state UNCERTAIN, pool counter unchanged). No new entry can fund itself
    on it (AC2). Only a reconciled terminal observation releases it."""
    now = now or _utcnow()
    row = _active(db, tenant_id, reservation_id)
    if row.state != "UNCERTAIN":
        row.state = "UNCERTAIN"
        row.version += 1
        row.updated_at = now
    db.flush()
    return row


def expire_reservations(
    db, tenant_id: uuid.UUID, *, now: datetime | None, valid_until_by_plan: dict[str, datetime]
) -> list[ReservationRow]:
    """Release active reservations whose plan's ``valid_until`` has passed."""
    now = now or _utcnow()
    released: list[ReservationRow] = []
    for plan_id, valid_until in sorted(valid_until_by_plan.items()):
        if valid_until > now:
            continue
        rows = list(
            db.scalars(
                select(ReservationRow).where(
                    ReservationRow.tenant_id == tenant_id,
                    ReservationRow.plan_id == plan_id,
                    ReservationRow.state.in_(ACTIVE_RESERVATION_STATES),
                )
            )
        )
        for row in rows:
            released.append(
                release_reservation(db, tenant_id, row.reservation_id, "EXPIRED", now=now)
            )
    return released


def _adjust_pool(
    db, tenant_id: uuid.UUID, account_id: str, delta: Decimal, now: datetime
) -> None:
    account = db.get(AccountAdmission, (tenant_id, account_id))
    if account is None:
        raise ReservationNotFound(f"account {account_id} has no admission row")
    new_reserved = account.cash_reserved + delta
    if new_reserved < 0:
        raise AdmissionError(
            f"pool invariant violated: reserved would go negative ({new_reserved})"
        )
    account.cash_reserved_text = _d(new_reserved)
    account.version += 1
    account.updated_at = now


def _active(db, tenant_id: uuid.UUID, reservation_id: str) -> ReservationRow:
    row = db.get(ReservationRow, reservation_id)
    if row is None or row.tenant_id != tenant_id:
        raise ReservationNotFound(f"reservation {reservation_id} does not exist for this tenant")
    if row.state not in ACTIVE_RESERVATION_STATES:
        raise AdmissionError(
            f"reservation {reservation_id} is {row.state}; only active reservations "
            "({'+'.join(ACTIVE_RESERVATION_STATES)}) can transition"
        )
    return row
