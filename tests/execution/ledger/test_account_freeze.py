"""AC5: no client-ID lookup + ambiguous existence -> account frozen for
conflicting entries until operator resolution."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from tests.execution.ledger.conftest import drive_child, make_request, ts

from algobots.execution.ledger import (
    AccountFrozen,
    apply_events,
    commit_intent,
    freeze_account,
    get_intent,
    resolve_freeze,
)
from algobots.execution.ledger.models import AccountFreeze


def test_ac5_ambiguous_existence_without_lookup_freezes_account(db, tenant):
    """GIVEN no client-ID lookup and ambiguous existence THEN the account
    remains frozen for conflicting entries until operator resolution."""
    intent_id, child, emulator, _ = drive_child(
        db,
        tenant,
        key="ac5-key-00000001",
        account="acct-ac5",
        faults={"accept_before_timeout", "no_client_id_lookup"},
    )
    db.refresh(child)
    assert child.state == "UNKNOWN"

    freezes = db.scalars(
        select(AccountFreeze).where(
            AccountFreeze.tenant_id == tenant, AccountFreeze.resolved_at.is_(None)
        )
    ).all()
    assert len(freezes) == 1
    assert freezes[0].reason == "AMBIGUOUS_EXISTENCE"
    assert get_intent(db, tenant, intent_id).account_frozen is True

    # conflicting entries are rejected while frozen...
    with pytest.raises(AccountFrozen):
        commit_intent(db, tenant, make_request(key="ac5-key-00000002", account="acct-ac5"))
    db.rollback()
    with pytest.raises(AccountFrozen):
        commit_intent(db, tenant, make_request(key="ac5-key-00000003", account="acct-ac5"))
    db.rollback()
    assert (
        db.scalar(
            select(func.count())
            .select_from(AccountFreeze)
            .where(AccountFreeze.tenant_id == tenant, AccountFreeze.resolved_at.is_(None))
        )
        == 1
    ), "one active freeze"

    # ...exits still flow (cancels are not conflicting entries)
    cancel = commit_intent(
        db, tenant, make_request(key="ac5-key-00000004", account="acct-ac5", action="CANCEL_ORDER")
    )
    db.commit()
    assert cancel.created

    # operator resolution: reconciliation found the order REJECTED broker-side
    resolution = [emulator.order_event(child, "REJECTED", reconciliation=True, when=ts(60))]
    assert all(r.applied for r in apply_events(db, tenant, resolution))
    db.commit()
    freeze = resolve_freeze(
        db, tenant, "acct-ac5", resolved_by="op-oncall", note="broker statement: order never booked"
    )
    db.commit()
    assert freeze.resolved_at is not None

    # after resolution the account accepts entries again
    after = commit_intent(db, tenant, make_request(key="ac5-key-00000005", account="acct-ac5"))
    db.commit()
    assert after.created


def test_freeze_is_idempotent_one_active_row(db, tenant):
    freeze_account(db, tenant, "acct-fz", reason="AMBIGUOUS_EXISTENCE")
    db.commit()
    again = freeze_account(db, tenant, "acct-fz", reason="AMBIGUOUS_EXISTENCE")
    db.commit()
    assert again.resolved_at is None
    active = db.scalars(
        select(AccountFreeze).where(
            AccountFreeze.tenant_id == tenant,
            AccountFreeze.account_id == "acct-fz",
            AccountFreeze.resolved_at.is_(None),
        )
    ).all()
    assert len(active) == 1


def test_freeze_is_tenant_scoped(db, tenant, tenant_b):
    freeze_account(db, tenant, "acct-shared", reason="AMBIGUOUS_EXISTENCE")
    db.commit()
    other = commit_intent(db, tenant_b, make_request(key="ac5-key-00000006", account="acct-shared"))
    db.commit()
    assert other.created, "another tenant on the same account label is not frozen"
