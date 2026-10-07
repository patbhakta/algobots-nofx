"""AC4: duplicate and out-of-order fills settle exactly once in projections."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from tests.execution.ledger.conftest import drive_child, ts

from algobots.execution.ledger import apply_events, get_intent
from algobots.execution.ledger.models import CashMovement, FillReceipt
from algobots.execution.ledger.service import SEP


def _movements(db, tenant, account):
    rows = db.scalars(
        select(CashMovement)
        .where(CashMovement.tenant_id == tenant, CashMovement.account_id == account)
        .order_by(CashMovement.movement_key)
    ).all()
    return {(r.kind, r.ref_id): Decimal(r.amount_text) for r in rows}


def test_ac4_duplicate_fill_settles_exactly_once(db, tenant):
    """GIVEN a fill repeated THEN cumulative fill, cash, and fees are correct
    exactly once in projections."""
    _, child, emulator, _ = drive_child(db, tenant, key="ac4-key-00000001", account="acct-ac4")
    fill = emulator.fill_event(
        child, qty="4", px="0.50", fee="0.14", broker_fill_id="ac4-f1", when=ts(20)
    )

    first = apply_events(db, tenant, [fill, fill.model_copy()])  # same fill, twice
    db.commit()
    assert [r.applied for r in first] == [True, False], "second delivery is a duplicate no-op"

    db.refresh(child)
    assert child.state == "PARTIALLY_FILLED"
    assert child.filled_qty == Decimal("4")
    assert Decimal(child.avg_px_text) == Decimal("0.50")
    assert child.fees == Decimal("0.14")
    movements = _movements(db, tenant, "acct-ac4")
    assert movements == {
        ("FILL_NOTIONAL", "ac4-f1"): Decimal("-2.00"),
        ("FEE", "ac4-f1"): Decimal("-0.14"),
    }, "cash settles exactly once"
    assert db.scalar(
        select(func.count())
        .select_from(FillReceipt)
        .where(FillReceipt.dedup_key.startswith(f"{tenant}{SEP}"))
    ) == 1


def test_ac4_partial_then_full_fill_projection(db, tenant):
    _, child, emulator, _ = drive_child(db, tenant, key="ac4-key-00000002", account="acct-ac4b")
    f1 = emulator.fill_event(
        child, qty="4", px="0.50", fee="0.14", broker_fill_id="ac4-g1", when=ts(20)
    )
    f2 = emulator.fill_event(
        child, qty="6", px="0.60", fee="0.21", broker_fill_id="ac4-g2", when=ts(21)
    )
    apply_events(db, tenant, [f1])
    db.commit()
    db.refresh(child)
    assert child.state == "PARTIALLY_FILLED"
    apply_events(db, tenant, [f2])
    db.commit()
    db.refresh(child)
    assert child.state == "FILLED"
    assert child.filled_qty == Decimal("10")
    assert Decimal(child.avg_px_text) == Decimal("0.56")  # (4*0.50 + 6*0.60) / 10
    assert child.fees == Decimal("0.35")
    movements = _movements(db, tenant, "acct-ac4b")
    assert movements[("FILL_NOTIONAL", "ac4-g1")] == Decimal("-2.00")
    assert movements[("FILL_NOTIONAL", "ac4-g2")] == Decimal("-3.60")
    assert movements[("FEE", "ac4-g1")] == Decimal("-0.14")
    assert movements[("FEE", "ac4-g2")] == Decimal("-0.21")


def test_ac4_out_of_order_delivery_is_cumulative_correct(db, tenant):
    """Fills delivered out of order produce the same cumulative projection,
    and re-delivering the whole batch changes nothing."""
    # order A: f1 then f2
    _, child_a, emu_a, _ = drive_child(db, tenant, key="ac4-key-00000003", account="acct-ac4c")
    f1 = emu_a.fill_event(
        child_a, qty="4", px="0.50", fee="0.14", broker_fill_id="ac4-h1", when=ts(20)
    )
    f2 = emu_a.fill_event(
        child_a, qty="6", px="0.60", fee="0.21", broker_fill_id="ac4-h2", when=ts(21)
    )
    apply_events(db, tenant, [f1, f2])
    db.commit()

    # order B: same economics, delivered reversed, then the batch re-delivered
    _, child_b, emu_b, _ = drive_child(db, tenant, key="ac4-key-00000004", account="acct-ac4d")
    g2 = emu_b.fill_event(
        child_b, qty="6", px="0.60", fee="0.21", broker_fill_id="ac4-h2", when=ts(20)
    )
    g1 = emu_b.fill_event(
        child_b, qty="4", px="0.50", fee="0.14", broker_fill_id="ac4-h1", when=ts(21)
    )
    results = apply_events(db, tenant, [g2, g1, g2.model_copy(), g1.model_copy()])
    db.commit()
    assert [r.applied for r in results] == [True, True, False, False]

    db.refresh(child_a)
    db.refresh(child_b)
    assert child_b.filled_qty == child_a.filled_qty == Decimal("10")
    assert child_b.avg_px_text == child_a.avg_px_text
    assert child_b.fees == child_a.fees == Decimal("0.35")
    assert child_b.state == child_a.state == "FILLED"
    assert len(_movements(db, tenant, "acct-ac4d")) == 4, "2 fills x 2 kinds, each settled once"


def test_ac4_fill_before_acknowledgment_is_deferred_not_dropped(db, tenant):
    """A fill that arrives BEFORE the acceptance carrying the broker<->client
    mapping is deferred inside the batch and applied once the mapping lands."""
    _, child, emulator, outbox = drive_child(
        db, tenant, key="ac4-key-00000005", account="acct-ac4e", acknowledge=False
    )
    broker_order_id = emulator.broker_order_id(outbox.command_id)
    early = emulator.fill_event(
        child, qty="4", broker_order_id=broker_order_id, broker_fill_id="ac4-i1", when=ts(20)
    )
    accept = emulator.order_event(child, "ACCEPTED", broker_order_id=broker_order_id, when=ts(21))
    results = apply_events(db, tenant, [early, accept])
    db.commit()
    assert all(r.applied for r in results), f"reordered batch converged: {results}"

    db.refresh(child)
    assert child.broker_order_id == broker_order_id
    assert child.state == "PARTIALLY_FILLED"
    assert child.filled_qty == Decimal("4")
    view = get_intent(db, tenant, child.intent_id)
    assert view.status == "PARTIALLY_FILLED"
    assert view.orders[0].filled_quantity == "4"


def test_ac4_delayed_cancel_after_partial_fill(db, tenant):
    """Cancel acknowledged late, after a partial fill: cumulative state stays
    correct (filled quantity survives the cancellation)."""
    from algobots.execution.ledger import request_cancel

    _, child, emulator, _ = drive_child(db, tenant, key="ac4-key-00000006", account="acct-ac4f")
    partial, fill, canceled = emulator.delayed_cancel_stream(child, when=ts(20))
    request_cancel(db, tenant, child.id)
    db.commit()
    db.refresh(child)
    assert child.state == "PENDING_CANCEL"
    results = apply_events(db, tenant, [partial, fill, canceled])
    db.commit()
    assert all(r.applied for r in results)
    db.refresh(child)
    assert child.state == "CANCELED"
    assert child.filled_qty == Decimal("4")
    assert child.fees == Decimal("0.07")
