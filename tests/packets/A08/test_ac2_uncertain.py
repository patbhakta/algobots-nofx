"""AC2: unknown orders and cancel-pending remainders retain obligations.

GIVEN an unknown order or cancel-pending remainder THEN its reservation
cannot fund a new conflicting entry. Only a reconciled terminal observation
releases the claim.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from algobots.execution.admission import (
    AdmissionDenied,
    admit_entry,
    get_or_create_admission,
    mark_uncertain,
    record_mark,
    release_reservation,
    resize_reservation,
    state_snapshot,
)
from algobots.execution.admission.models import AccountAdmission, ReservationRow

from .conftest import make_plan, make_policy, make_proposal, make_request

D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)


def _admit(db, tenant, *, instrument="KXA8.DEMO", key="k", plan_id="p", qty="7"):
    record_mark(
        db, tenant, "acct-u", instrument,
        price=D("100"), currency="USD", quality="REALTIME", observed_at=NOW,
    )
    snapshot = state_snapshot(db, tenant, "acct-u", instrument, equity_reference=D("1000"))
    payload = {"instrument": instrument, "side": "BUY", "quantity": qty}
    return admit_entry(
        db, tenant, make_policy(account="acct-u"),
        make_proposal(account="acct-u", instrument=instrument, qty=qty),
        make_request(key=key, account="acct-u", payload=payload),
        make_plan(account="acct-u", qty=qty, plan_id=plan_id, instrument=instrument),
        state=snapshot, now=NOW,
    )


def test_unknown_order_reservation_cannot_fund_new_entry(db, tenant):
    get_or_create_admission(db, tenant, "acct-u", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="unk-key-000001", plan_id="plan-unk-a")  # $700 HELD
    db.commit()

    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-unk-a"
        )
    )

    # the broker answer becomes ambiguous → UNKNOWN: the obligation RETAINS
    mark_uncertain(db, tenant, row.reservation_id)
    db.commit()
    db.refresh(row)
    assert row.state == "UNCERTAIN"

    # $300 unreserved: a new $700 entry cannot fund itself on the uncertain one
    with pytest.raises((AdmissionDenied, Exception)) as exc:
        _admit(db, tenant, instrument="KXB8.DEMO", key="unk-key-000002", plan_id="plan-unk-b")
    db.rollback()
    assert "insufficient_funds" in str(exc.value) or "overcommit" in str(exc.value).lower()
    account = db.get(AccountAdmission, (tenant, "acct-u"))
    assert account.cash_reserved == D("700"), "UNCERTAIN keeps its claim"

    # only a RECONCILED terminal observation releases it
    released = release_reservation(db, tenant, row.reservation_id, "RECONCILED_REJECTION")
    db.commit()
    assert released.state == "RELEASED" and released.release_reason == "RECONCILED_REJECTION"
    db.refresh(account)
    assert account.cash_reserved == D("0")


def test_cancel_pending_remainder_retains_obligation(db, tenant):
    """A partially-filled order moves to PENDING_CANCEL: the unfilled
    remainder stays obligated until the cancel is reconciled."""
    get_or_create_admission(db, tenant, "acct-u", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="cxl-key-000001", plan_id="plan-cxl-a")
    db.commit()
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-cxl-a"
        )
    )

    # partial fill: 3 of 7 filled → remainder resized, still HELD
    resize_reservation(
        db, tenant, row.reservation_id, new_amount=D("400.00"), reason="PARTIAL_FILL"
    )
    db.commit()
    db.refresh(row)
    assert row.state == "HELD" and row.amount == D("400.00")

    # cancel requested, not yet reconciled → UNCERTAIN retains the remainder
    mark_uncertain(db, tenant, row.reservation_id)
    db.commit()
    account = db.get(AccountAdmission, (tenant, "acct-u"))
    assert account.cash_reserved == D("400.00")
    with pytest.raises((AdmissionDenied, Exception)):
        _admit(db, tenant, instrument="KXB8.DEMO", key="cxl-key-000002", plan_id="plan-cxl-b")
    db.rollback()

    # reconciled CANCELED releases the remainder
    release_reservation(db, tenant, row.reservation_id, "CANCELED")
    db.commit()
    db.refresh(account)
    assert account.cash_reserved == D("0")


def test_double_release_is_rejected(db, tenant):
    from algobots.execution.admission import AdmissionError

    get_or_create_admission(db, tenant, "acct-u", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="dbl-key-000001", plan_id="plan-dbl-a")
    db.commit()
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-dbl-a"
        )
    )
    release_reservation(db, tenant, row.reservation_id, "CANCELED")
    db.commit()
    with pytest.raises(AdmissionError):
        release_reservation(db, tenant, row.reservation_id, "CANCELED")
    db.rollback()


def test_release_requires_a_known_reason(db, tenant):
    from algobots.execution.admission import AdmissionError

    get_or_create_admission(db, tenant, "acct-u", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="rsn-key-000001", plan_id="plan-rsn-a")
    db.commit()
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-rsn-a"
        )
    )
    with pytest.raises(AdmissionError):
        release_reservation(db, tenant, row.reservation_id, "BECAUSE")
    db.rollback()


def test_db_check_released_row_requires_reason(db, tenant):
    """The DB-level CHECK: state=RELEASED must carry release_reason."""
    from sqlalchemy import text
    from sqlalchemy.exc import IntegrityError

    get_or_create_admission(db, tenant, "acct-u", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="chk-key-000001", plan_id="plan-chk-a")
    db.commit()
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-chk-a"
        )
    )
    with pytest.raises(IntegrityError):
        db.execute(
            text(
                "UPDATE reservations SET state = 'RELEASED', release_reason = NULL "
                "WHERE reservation_id = :rid"
            ),
            {"rid": row.reservation_id},
        )
        db.commit()
    db.rollback()
