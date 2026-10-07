"""Recovery: outbox replay with stable identities, unresolved commands and
reservations preserved across a session loss."""

from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from tests.execution.ledger.conftest import drive_child, ts
from tests.execution.ledger.emulator import BrokerEmulator

from algobots.execution.ledger import dispatch_pending, stage_commands
from algobots.execution.ledger.models import IntentOutbox, OrderPlanRow


def test_recovery_preserves_unresolved_command_and_replays_stable_identity(
    db, ledger_engine, tenant
):
    """Unresolved commands and reservations survive a 'crash' (session loss);
    replay re-delivers the SAME event/command identity and the seam
    deduplicates it — one external order, ever."""
    _, child, emulator, outbox = drive_child(
        db, tenant, key="rec-key-00000001", account="acct-rec", faults={"connection_drop"}
    )
    db.commit()
    db.close()  # crash: the session (and everything un-persisted) is gone

    # a fresh session sees the durable state: plan + reservations + PENDING row
    db2 = sessionmaker(bind=ledger_engine, expire_on_commit=False)()
    try:
        plan_row = db2.scalar(select(OrderPlanRow).where(OrderPlanRow.intent_id == child.intent_id))
        assert plan_row is not None
        reservations = json.loads(plan_row.reservations_json)
        assert len(reservations) == 1 and reservations[0]["state"] == "HELD"
        assert json.loads(plan_row.plan_json)["plan_id"] == plan_row.plan_id

        pending = db2.scalar(select(IntentOutbox).where(IntentOutbox.event_id == outbox.event_id))
        assert pending.status == "PENDING" and pending.attempts == 1
        original_command = pending.command_json
        original_emitted = pending.emitted_at

        # replay with a healthy seam
        healthy = BrokerEmulator()
        report = dispatch_pending(db2, healthy, tenant_id=tenant)
        db2.commit()
        assert report.delivered == 1
        assert healthy.order_count == 1
        assert healthy.submit_log[0][1] == emulator.submit_log[0][1], "same command_id"
        db2.refresh(pending)
        assert pending.status == "DISPATCHED"
        assert pending.command_json == original_command, "command payload never re-minted"
        assert pending.emitted_at == original_emitted, "stable identity across replay"
        assert db2.scalar(
            select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
        ) == 1

        # reservations are still intact after recovery + replay
        reservations_after = json.loads(
            db2.scalar(
                select(OrderPlanRow.reservations_json).where(
                    OrderPlanRow.plan_id == plan_row.plan_id
                )
            )
        )
        assert reservations_after == reservations
    finally:
        db2.close()


def test_dispatched_rows_are_not_redelivered(db, tenant):
    _, child, emulator, outbox = drive_child(
        db, tenant, key="rec-key-00000002", account="acct-rec2"
    )
    row = db.get(IntentOutbox, outbox.event_id)
    assert row.status == "DISPATCHED"
    report = dispatch_pending(db, emulator, tenant_id=tenant)
    db.commit()
    assert report.attempted == 0, "DISPATCHED rows leave the pending set"
    assert emulator.order_count == 1


def test_staging_is_idempotent_per_epoch_and_versioned_across_epochs(db, tenant):
    intent_id, child, _, _ = drive_child(
        db, tenant, key="rec-key-00000003", account="acct-rec3", faults={"connection_drop"}
    )
    # same epoch: re-derive the same event id -> no second row
    stage_commands(db, tenant, intent_id, ownership_epoch=0, policy_revision="r1", deadline=ts(600))
    db.commit()
    assert db.scalar(
        select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
    ) == 1

    # a new ownership epoch is a NEW command identity (ownership handoff), and
    # both identities are durable: replay delivers in order
    stage_commands(db, tenant, intent_id, ownership_epoch=1, policy_revision="r1", deadline=ts(900))
    db.commit()
    assert db.scalar(
        select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
    ) == 2
    emulator = BrokerEmulator()
    report = dispatch_pending(db, emulator, tenant_id=tenant)
    db.commit()
    assert report.delivered == 2
    assert emulator.order_count == 2, "two epochs = two distinct commands"
    ids = [cmd for _, cmd, _ in emulator.submit_log]
    assert len(set(ids)) == 2
