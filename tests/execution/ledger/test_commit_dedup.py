"""AC1/AC2: concurrent duplicate commits, key/payload conflicts, entry guard."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker
from tests.execution.ledger.conftest import (
    drive_child,
    make_plan,
    make_request,
    make_reservation,
    ts,
)
from tests.execution.ledger.emulator import BrokerEmulator

from algobots.execution.ledger import (
    GuardRejected,
    IdempotencyConflict,
    attach_plan,
    commit_intent,
    dispatch_pending,
    get_intent,
    stage_commands,
)
from algobots.execution.ledger.models import ChildOrder, ExecutionIntent, IntentOutbox


def test_ac1_one_request_sent_1000_times_concurrently_yields_one_intent(db, ledger_engine, tenant):
    """GIVEN one request sent 1,000 times concurrently THEN one intent exists
    and at most one confirmed external order is created."""
    request = make_request(key="ac1-key-00000001", account="acct-ac1")

    def submit_one(_: int):
        session = sessionmaker(bind=ledger_engine, expire_on_commit=False)()
        try:
            result = commit_intent(session, tenant, request)
            session.commit()
            return result
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(pool.map(submit_one, range(1000)))

    assert len(results) == 1000
    creators = [r for r in results if r.created]
    assert len(creators) == 1, "exactly one caller creates the intent"
    assert {r.intent_id for r in results} == {creators[0].intent_id}
    assert db.scalar(
        select(func.count()).select_from(ExecutionIntent).where(ExecutionIntent.tenant_id == tenant)
    ) == 1

    # ... and at most one confirmed external order after staging + dispatch
    plan = make_plan(creators[0].intent_id, account="acct-ac1")
    attach_plan(db, tenant, creators[0].intent_id, plan, [make_reservation(plan)])
    stage_commands(
        db,
        tenant,
        creators[0].intent_id,
        ownership_epoch=0,
        policy_revision="risk-rev-1",
        deadline=ts(300),
    )
    db.commit()
    emulator = BrokerEmulator()
    report = dispatch_pending(db, emulator, tenant_id=tenant)
    db.commit()
    assert report.delivered == 1
    assert emulator.order_count == 1, "at most one confirmed external order"
    assert db.scalar(
        select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
    ) == 1
    assert db.scalar(
        select(func.count()).select_from(ChildOrder).where(ChildOrder.tenant_id == tenant)
    ) == 1
    assert get_intent(db, tenant, creators[0].intent_id).status == "SUBMITTED"


def test_ac2_same_key_changed_payload_is_rejected_original_untouched(db, tenant):
    """GIVEN identical key with changed quantity THEN request is rejected
    without altering the original intent."""
    original = make_request(key="ac2-key-00000001", account="acct-ac2")
    first = commit_intent(db, tenant, original)
    db.commit()
    assert first.created

    changed = make_request(
        key="ac2-key-00000001",
        account="acct-ac2",
        payload={"instrument": "KXA7.DEMO", "side": "BUY", "quantity": "20"},
    )
    with pytest.raises(IdempotencyConflict):
        commit_intent(db, tenant, changed)
    db.rollback()

    row = db.get(ExecutionIntent, first.intent_id)
    assert row.payload_hash == original.payload_hash
    assert json.loads(row.payload_json)["quantity"] == "10", "original payload untouched"
    assert row.status == "ACCEPTED"

    again = commit_intent(db, tenant, original)  # identical request still dedups
    assert again.created is False and again.intent_id == first.intent_id


def test_active_entry_guard_blocks_same_business_signal_with_different_keys(db, tenant):
    """Repeated business signal under a DIFFERENT transport key cannot open a
    second active entry while the first is active."""
    commit_intent(db, tenant, make_request(key="guard-key-0001", account="acct-g"))
    db.commit()
    with pytest.raises(GuardRejected):
        commit_intent(db, tenant, make_request(key="guard-key-0002", account="acct-g"))
    db.rollback()
    assert db.scalar(
        select(func.count()).select_from(ExecutionIntent).where(ExecutionIntent.tenant_id == tenant)
    ) == 1


def test_guard_lifts_when_entry_reaches_terminal_state(db, tenant):
    """Once the first entry is terminal, the same business signal may re-enter."""
    intent_id, child, emulator, _ = drive_child(db, tenant, key="lift-key-00001", account="acct-l")
    fill = emulator.fill_event(child, qty="10", broker_fill_id="lift-fill-1", when=ts(20))
    from algobots.execution.ledger import apply_fill_event

    apply_fill_event(db, tenant, fill)
    db.commit()
    assert child.state == "FILLED"

    second = commit_intent(db, tenant, make_request(key="lift-key-00002", account="acct-l"))
    db.commit()
    assert second.created and second.intent_id != intent_id


def test_non_entry_actions_are_not_guarded(db, tenant):
    """CANCEL intents are exits, not entries: the guard must not block them."""
    commit_intent(
        db, tenant, make_request(key="cancel-key-0001", account="acct-c", action="CANCEL_ORDER")
    )
    second = commit_intent(
        db,
        tenant,
        make_request(key="cancel-key-0002", account="acct-c", action="CANCEL_ORDER"),
    )
    db.commit()
    assert second.created


def test_frozen_account_rejects_entries_but_not_cancels(db, tenant):
    """While an account is frozen, entry intents are rejected (423) and
    cancels still flow."""
    from algobots.execution.ledger import AccountFrozen, freeze_account

    freeze_account(db, tenant, "acct-f", reason="AMBIGUOUS_EXISTENCE")
    db.commit()
    with pytest.raises(AccountFrozen):
        commit_intent(db, tenant, make_request(key="frz-key-000001", account="acct-f"))
    db.rollback()
    cancel = commit_intent(
        db, tenant, make_request(key="frz-key-000002", account="acct-f", action="CANCEL_ORDER")
    )
    db.commit()
    assert cancel.created
