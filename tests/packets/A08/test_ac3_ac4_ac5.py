"""AC3 + AC4 + AC5 through the admission path, plus the entry-pause demo law."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from algobots.execution.admission import (
    AdmissionDenied,
    admit_entry,
    consume_on_fill,
    expire_reservations,
    get_controls,
    get_or_create_admission,
    record_mark,
    set_controls,
    state_snapshot,
)
from algobots.execution.admission.models import ReservationRow
from algobots.risk.controls import AccountControls, ControlAction, check_action

from .conftest import T0, make_plan, make_policy, make_proposal, make_request

D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)


def _setup(db, tenant, *, cash="1000", account="acct-m"):
    get_or_create_admission(db, tenant, account, cash=D(cash))
    db.commit()


def _snapshot(db, tenant, instrument="KXA8.DEMO", *, daily_pnl=D("0"), account="acct-m"):
    record_mark(
        db, tenant, account, instrument,
        price=D("100"), currency="USD", quality="REALTIME", observed_at=NOW,
    )
    return state_snapshot(
        db, tenant, account, instrument, equity_reference=D("1000"), daily_pnl=daily_pnl
    )


def _admit(db, tenant, *, key="k", plan_id="p", instrument="KXA8.DEMO", qty="7",
           kind="ENTRY", daily_pnl=D("0"), account="acct-m", policy=None):
    payload = {"instrument": instrument, "side": "BUY", "quantity": qty}
    return admit_entry(
        db, tenant, policy or make_policy(account=account),
        make_proposal(account=account, instrument=instrument, qty=qty, kind=kind),
        make_request(key=key, account=account, payload=payload),
        make_plan(account=account, qty=qty, plan_id=plan_id, instrument=instrument),
        state=_snapshot(db, tenant, instrument, daily_pnl=daily_pnl, account=account),
        now=NOW,
    )


# -- AC3: breached daily loss cap ---------------------------------------------


def test_ac3_daily_loss_breach_denies_entries_allows_risk_reducing(db, tenant):
    _setup(db, tenant)
    policy = make_policy(account="acct-m", max_daily_loss="200.00")
    breached = D("-250")  # loss 250 >= cap 200

    with pytest.raises(AdmissionDenied) as exc:
        _admit(
            db, tenant, key="dl-key-000001", plan_id="plan-dl-a",
            daily_pnl=breached, policy=policy,
        )
    db.rollback()
    assert exc.value.decision.rule == "daily_loss"
    assert "risk-reducing actions remain possible" in exc.value.decision.reason

    # a risk-reducing action is still admissible while the cap is breached
    # (funds are not consumed by REDUCE; the intent is committed)
    result = _admit(
        db, tenant, key="dl-key-000002", plan_id="plan-dl-b",
        kind="REDUCE", daily_pnl=breached, policy=policy,
    )
    db.commit()
    assert result.decision.decision == "APPROVE"


def test_ac3_entry_pause_via_controls_denies_entries_not_reductions(db, tenant):
    _setup(db, tenant)
    set_controls(db, tenant, "acct-m", AccountControls(entries_paused=True))
    db.commit()

    with pytest.raises(AdmissionDenied) as exc:
        _admit(db, tenant, key="pz-key-000001", plan_id="plan-pz-a")
    db.rollback()
    assert exc.value.decision.rule == "account_control"
    assert "paused" in exc.value.decision.reason

    reduce_ = _admit(db, tenant, key="pz-key-000002", plan_id="plan-pz-b", kind="REDUCE")
    db.commit()
    assert reduce_.decision.decision == "APPROVE"

    # the pause is visible and does NOT touch protective actions
    controls = get_controls(db, tenant, "acct-m")
    assert controls.entries_paused
    assert check_action(controls, ControlAction.PROTECTIVE).allowed
    assert not check_action(controls, ControlAction.ENTRY).allowed


# -- AC4: AI proposal above policy → deterministic clamp, then re-plan --------


def test_ac4_oversize_ai_proposal_rejected_then_admitted_at_clamped_size(db, tenant):
    _setup(db, tenant)
    policy = make_policy(account="acct-m", max_order="500.00")

    # the AI proposes $700; the plan carries $700 → admission fails closed:
    # the plan must be re-planned at the clamped size (no silent shrink)
    with pytest.raises(Exception) as exc:
        _admit(db, tenant, key="ai-key-000001", plan_id="plan-ai-a", policy=policy)
    db.rollback()
    assert "re-plan at the approved size" in str(exc.value)

    # re-planned at the clamped $500 → admitted, with the clamp on record
    result = _admit(db, tenant, key="ai-key-000002", plan_id="plan-ai-b", qty="5", policy=policy)
    db.commit()
    assert result.decision.decision == "APPROVE"
    assert result.reserved == D("500")
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-ai-b"
        )
    )
    assert row.claim == D("500")


# -- AC5: stale state / reconnect ----------------------------------------------


def test_ac5_stale_mark_blocks_new_risk_until_fresh(db, tenant):
    _setup(db, tenant)
    stale_time = NOW - timedelta(seconds=120)
    record_mark(
        db, tenant, "acct-m", "KXA8.DEMO",
        price=D("100"), currency="USD", quality="STALE_CACHE", observed_at=stale_time,
    )
    snapshot = state_snapshot(db, tenant, "acct-m", "KXA8.DEMO", equity_reference=D("1000"))
    with pytest.raises(AdmissionDenied) as exc:
        admit_entry(
            db, tenant, make_policy(account="acct-m"),
            make_proposal(account="acct-m"),
            make_request(key="st-key-000001", account="acct-m"),
            make_plan(account="acct-m", plan_id="plan-st-a"),
            state=snapshot, now=NOW,
        )
    db.rollback()
    assert exc.value.decision.rule == "stale_state"

    # fresh state unblocks; the protection status is visible throughout
    fresh = _snapshot(db, tenant)
    result = admit_entry(
        db, tenant, make_policy(account="acct-m"),
        make_proposal(account="acct-m"),
        make_request(key="st-key-000002", account="acct-m"),
        make_plan(account="acct-m", plan_id="plan-st-b"),
        state=fresh, now=NOW,
    )
    db.commit()
    assert result.decision.decision == "APPROVE"


def test_ac5_protection_status_visible_during_outage(db, tenant):
    """Reconnect/stale-mark: controls stay readable, protections listed."""
    from algobots.contracts.enums import OrderSide, OrderType
    from algobots.risk.controls import (
        ProtectionOrder,
        protection_status,
    )

    set_controls(db, tenant, "acct-m", AccountControls(entries_paused=True))
    db.commit()
    status = protection_status(
        get_controls(db, tenant, "acct-m"),
        (
            ProtectionOrder(
                instrument_id="KXA8.DEMO",
                order_type=OrderType.STOP,
                protection="stop",
                side=OrderSide.SELL,
                quantity=D("7"),
                working=True,
            ),
        ),
    )
    assert status.entries_paused and status.new_risk_blocked
    assert status.working_protections == 1, "pause kept the stop working"


# -- lifecycle: fill consumption + expiry --------------------------------------


def test_fill_consumes_reservation_and_charges_pool(db, tenant):
    _setup(db, tenant)
    _admit(db, tenant, key="fl-key-000001", plan_id="plan-fl-a")
    db.commit()
    row = db.scalar(
        select(ReservationRow).where(
            ReservationRow.tenant_id == tenant, ReservationRow.plan_id == "plan-fl-a"
        )
    )
    consume_on_fill(
        db, tenant, row.reservation_id, settle_amount=D("700"), now=NOW
    )
    db.commit()
    db.refresh(row)
    assert row.state == "CONSUMED" and row.release_reason == "FILLED"
    from algobots.execution.admission.models import AccountAdmission

    account = db.get(AccountAdmission, (tenant, "acct-m"))
    assert account.cash_reserved == D("0")
    assert account.cash_available == D("300"), "settled notional left the pool"


def test_expiry_releases_stale_plans(db, tenant):
    _setup(db, tenant)
    _admit(db, tenant, key="ex-key-000001", plan_id="plan-ex-a")
    db.commit()
    released = expire_reservations(
        db,
        tenant,
        now=T0 + timedelta(hours=2),
        valid_until_by_plan={"plan-ex-a": T0 + timedelta(hours=1)},
    )
    db.commit()
    assert len(released) == 1 and released[0].release_reason == "EXPIRED"
    from algobots.execution.admission.models import AccountAdmission

    account = db.get(AccountAdmission, (tenant, "acct-m"))
    assert account.cash_reserved == D("0")
