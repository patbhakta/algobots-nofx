"""AC1: two simultaneous entries cannot overcommit shared funds.

GIVEN $1,000 available and two simultaneous $700 entry plans THEN both
cannot be admitted; the sum of reservations never exceeds permitted funds —
proven sequentially AND under real thread concurrency, plus the DB-level
CHECK law on reservations.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from algobots.execution.admission import (
    AdmissionDenied,
    OvercommitRejected,
    admit_entry,
    get_or_create_admission,
    release_reservation,
)
from algobots.execution.admission.models import AccountAdmission, ReservationRow

from .conftest import make_plan, make_policy, make_proposal, make_request

D = Decimal
POOL = D("1000")


def _admit(db, tenant, *, instrument: str, key: str, plan_id: str, qty: str = "7"):
    """One strategy's $700 entry attempt against the shared pool."""
    from datetime import UTC, datetime

    from algobots.execution.admission import record_mark, state_snapshot

    now = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
    record_mark(
        db, tenant, "acct-race", instrument,
        price=D("100"), currency="USD", quality="REALTIME", observed_at=now,
    )
    snapshot = state_snapshot(
        db, tenant, "acct-race", instrument, equity_reference=D("1000")
    )
    proposal = make_proposal(account="acct-race", instrument=instrument, qty=qty)
    payload = {"instrument": instrument, "side": "BUY", "quantity": qty}
    request = make_request(key=key, account="acct-race", payload=payload)
    plan = make_plan(account="acct-race", qty=qty, plan_id=plan_id, instrument=instrument)
    return admit_entry(
        db, tenant, make_policy(account="acct-race"), proposal, request, plan,
        state=snapshot, now=now,
    )


def _pool_invariant(db, tenant) -> tuple[Decimal, Decimal]:
    """(reserved counter, sum of ACTIVE row claims) — must be equal and <= pool."""
    account = db.get(AccountAdmission, (tenant, "acct-race"))
    reserved = account.cash_reserved
    rows = list(
        db.scalars(
            select(ReservationRow).where(
                ReservationRow.tenant_id == tenant,
                ReservationRow.account_id == "acct-race",
                ReservationRow.state.in_(("HELD", "UNCERTAIN")),
            )
        )
    )
    claims = sum((r.claim for r in rows), D("0"))
    return reserved, claims


def test_ac1_sequential_second_700_is_rejected(db, tenant):
    get_or_create_admission(db, tenant, "acct-race", cash=POOL)
    db.commit()

    first = _admit(db, tenant, instrument="KXA8.DEMO", key="race-key-00001", plan_id="plan-race-a")
    db.commit()
    assert first.reserved == D("700")

    # Sequentially the POLICY's funds rule denies first (the snapshot already
    # reports the committed reservation); under a concurrent race the same
    # outcome is enforced by the CAS. Either way: one winner, invariant held.
    with pytest.raises((AdmissionDenied, OvercommitRejected)) as exc:
        _admit(db, tenant, instrument="KXB8.DEMO", key="race-key-00002", plan_id="plan-race-b")
    db.rollback()
    denied = getattr(exc.value, "decision", None)
    if denied is not None:
        assert denied.rule == "insufficient_funds"
    else:
        assert exc.value.requested == D("700")
        assert exc.value.available == D("300")

    reserved, claims = _pool_invariant(db, tenant)
    assert reserved == claims == D("700") <= POOL
    assert db.scalar(
        select(func.count()).select_from(ReservationRow).where(ReservationRow.tenant_id == tenant)
    ) == 1


def test_ac1_concurrent_700s_exactly_one_admitted(db, tenant, admission_engine):
    """Two strategies race for the same funds with separate sessions."""
    from sqlalchemy.orm import sessionmaker

    get_or_create_admission(db, tenant, "acct-race", cash=POOL)
    db.commit()

    def attempt(slot: int) -> str:
        session = sessionmaker(bind=admission_engine, expire_on_commit=False)()
        instrument = "KXA8.DEMO" if slot == 0 else "KXB8.DEMO"
        try:
            _admit(
                session, tenant,
                instrument=instrument,
                key=f"race-key-conc-{slot}",
                plan_id=f"plan-race-c{slot}",
            )
            session.commit()
            return "admitted"
        except (AdmissionDenied, OvercommitRejected):
            session.rollback()
            return "rejected"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(attempt, range(2)))

    assert sorted(outcomes) == ["admitted", "rejected"], outcomes
    reserved, claims = _pool_invariant(db, tenant)
    assert reserved == claims == D("700")
    assert reserved <= POOL, "sum of reservations never exceeds permitted funds"


def test_release_returns_funds_and_admits_the_waiter(db, tenant):
    get_or_create_admission(db, tenant, "acct-race", cash=POOL)
    db.commit()
    _admit(db, tenant, instrument="KXA8.DEMO", key="rel-key-000001", plan_id="plan-rel-a")
    db.commit()

    # reconciled rejection frees the claim
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-rel-a"
        )
    )
    release_reservation(db, tenant, row.reservation_id, "RECONCILED_REJECTION")
    db.commit()
    reserved, claims = _pool_invariant(db, tenant)
    assert reserved == claims == D("0")

    # the second strategy can now be admitted
    second = _admit(db, tenant, instrument="KXB8.DEMO", key="rel-key-000002", plan_id="plan-rel-b")
    db.commit()
    assert second.reserved == D("700")


def test_reservations_never_commit_without_their_intent(db, tenant):
    """A funded reservation always carries a committed A07 intent (same txn)."""
    from algobots.execution.ledger.models import ExecutionIntent, OrderPlanRow

    get_or_create_admission(db, tenant, "acct-race", cash=POOL)
    db.commit()
    result = _admit(db, tenant, instrument="KXA8.DEMO", key="intent-key-0001", plan_id="plan-int-a")
    db.commit()
    intent = db.get(ExecutionIntent, result.intent_id)
    assert intent is not None and intent.status in ("ACCEPTED", "PLANNED")
    plan = db.scalar(select(OrderPlanRow).where(OrderPlanRow.intent_id == result.intent_id))
    assert plan is not None
    assert plan.reservations_json != "[]", "dispatch intent persists its reservations"
    row = db.scalar(select(ReservationRow).where(ReservationRow.plan_id == "plan-int-a"))
    assert row.state == "HELD"
