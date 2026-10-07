"""AC3: broker accepts then connection times out -> UNKNOWN, no blind
resubmit, reconciliation finds the original order."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from tests.execution.ledger.conftest import drive_child, ts

from algobots.execution.ledger import (
    apply_events,
    dispatch_pending,
    get_intent,
    replay_outbox,
    stage_commands,
)
from algobots.execution.ledger.errors import LedgerError
from algobots.execution.ledger.models import IntentOutbox


def test_ac3_accept_before_timeout_becomes_unknown_without_blind_resubmit(db, tenant):
    """GIVEN broker accepts then connection times out THEN status becomes
    UNKNOWN and no blind resubmit occurs; reconciliation finds the original."""
    intent_id, child, emulator, outbox = drive_child(
        db, tenant, key="ac3-key-00000001", account="acct-ac3", faults={"accept_before_timeout"}
    )

    # the broker DID accept exactly one order...
    assert emulator.order_count == 1
    broker_order_id = emulator.broker_order_id(outbox.command_id)
    # ...but the ledger saw a timeout: child + intent are UNKNOWN
    db.refresh(child)
    assert child.state == "UNKNOWN"
    assert get_intent(db, tenant, intent_id).status == "UNKNOWN"

    # no blind resubmit: re-staging (any epoch) refuses UNKNOWN children...
    with pytest.raises(LedgerError, match="blind resubmit"):
        stage_commands(
            db, tenant, intent_id, ownership_epoch=1, policy_revision="risk-rev-1", deadline=ts(600)
        )
    db.rollback()
    # ...and no second outbox row was ever created
    assert db.scalar(
        select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
    ) == 1

    # replaying the SAME stable identity is not a resubmit: the broker
    # deduplicates the command and still holds exactly one order
    report = replay_outbox(db, emulator, tenant_id=tenant)
    db.commit()
    assert report.ambiguous == 0 and report.delivered == 1
    assert emulator.order_count == 1
    row = db.get(IntentOutbox, outbox.event_id)
    assert row.status == "DISPATCHED" and row.attempts == 2

    # reconciliation finds the original order and the state resolves
    reconciliation = [
        emulator.order_event(
            child, "ACCEPTED", broker_order_id=broker_order_id, reconciliation=True, when=ts(30)
        ),
        emulator.fill_event(
            child,
            qty="10",
            broker_order_id=broker_order_id,
            broker_fill_id="ac3-fill-1",
            when=ts(31),
        ),
    ]
    results = apply_events(db, tenant, reconciliation)
    db.commit()
    assert all(r.applied for r in results)
    db.refresh(child)
    assert child.state == "FILLED"
    assert child.broker_order_id == broker_order_id
    view = get_intent(db, tenant, intent_id)
    assert view.status == "FILLED"
    assert view.orders[0].broker_order_id == broker_order_id


def test_unknown_cannot_be_exited_by_a_non_reconciliation_event(db, tenant):
    """A plain (non-reconciliation) ACKNOWLEDGED for an UNKNOWN order is
    refused: only reconciliation-origin observations resolve UNKNOWN."""
    from algobots.execution.ledger import apply_order_event
    from algobots.execution.ledger.errors import IllegalTransitionError

    intent_id, child, emulator, outbox = drive_child(
        db, tenant, key="ac3-key-00000002", account="acct-ac3b", faults={"accept_before_timeout"}
    )
    assert child.state == "UNKNOWN"
    with pytest.raises(IllegalTransitionError):
        apply_order_event(
            db,
            tenant,
            emulator.order_event(
                child,
                "ACCEPTED",
                broker_order_id=emulator.broker_order_id(outbox.command_id),
                when=ts(30),
            ),
        )
    db.rollback()
    db.refresh(child)
    assert child.state == "UNKNOWN"


def test_connection_drop_stays_pending_and_recovers_via_replay(db, tenant):
    """A drop BEFORE delivery is unambiguous: the child keeps SUBMITTED and
    the PENDING row replays with the same identity after recovery."""
    intent_id, child, emulator, outbox = drive_child(
        db, tenant, key="ac3-key-00000003", account="acct-ac3c", faults={"connection_drop"}
    )
    assert child.state == "SUBMITTED"
    row = db.get(IntentOutbox, outbox.event_id)
    assert row.status == "PENDING" and row.attempts == 1
    assert emulator.order_count == 0

    healthy = type(emulator)()  # same sink contract, no faults armed
    report = dispatch_pending(db, healthy, tenant_id=tenant)
    db.commit()
    assert report.delivered == 1
    assert healthy.order_count == 1
    assert healthy.submit_log[0][1] == emulator.submit_log[0][1], "same command identity"
    assert get_intent(db, tenant, intent_id).status == "SUBMITTED"
