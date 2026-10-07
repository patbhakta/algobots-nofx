"""ALG-3306 review findings F1/F2 folded: regression tests.

- F1: deposits take the same CAS discipline as admissions; a withdrawal may
  never strand active reservations below their claims.
- F2: a multi-child plan at the exact rounding boundary (per-row claims
  quantized separately vs the policy's whole-notional quantization) is NOT
  spuriously rejected — the comparison tolerates one cent per reservation
  row and no more.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from algobots.contracts.base import Money
from algobots.contracts.enums import IntentAction
from algobots.contracts.plan import ChildOrder, OrderPlan, canonical_hash
from algobots.execution.admission import (
    AdmissionError,
    admit_entry,
    deposit,
    get_or_create_admission,
    record_mark,
    state_snapshot,
)
from algobots.execution.admission.models import AccountAdmission, ReservationRow

from .conftest import T0, make_plan, make_policy, make_proposal, make_request

D = Decimal
NOW = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)


def _admit(db, tenant, *, key, plan_id, instrument="KXA8.DEMO", qty="3"):
    record_mark(
        db, tenant, "acct-f1", instrument,
        price=D("100"), currency="USD", quality="REALTIME", observed_at=NOW,
    )
    snapshot = state_snapshot(
        db, tenant, "acct-f1", instrument, equity_reference=D("1000")
    )
    payload = {"instrument": instrument, "side": "BUY", "quantity": qty}
    return admit_entry(
        db, tenant, make_policy(account="acct-f1"),
        make_proposal(account="acct-f1", instrument=instrument, qty=qty),
        make_request(key=key, account="acct-f1", payload=payload),
        make_plan(account="acct-f1", qty=qty, plan_id=plan_id, instrument=instrument),
        state=snapshot, now=NOW,
    )


# -- F1 ------------------------------------------------------------------------


def test_f1_withdrawal_cannot_strand_active_reservations(db, tenant):
    get_or_create_admission(db, tenant, "acct-f1", cash=D("1000"))
    db.commit()
    _admit(db, tenant, key="f1-key-000001", plan_id="plan-f1-a", qty="7")  # 700 HELD
    db.commit()
    # withdrawing 400 would leave 300 available < 700 reserved: refused
    with pytest.raises(AdmissionError) as exc:
        deposit(db, tenant, "acct-f1", D("-400"))
    db.rollback()
    assert "strand active reservations" in str(exc.value)
    # withdrawing 300 leaves exactly the reserved amount: allowed
    row = deposit(db, tenant, "acct-f1", D("-300"))
    db.commit()
    assert row.cash_available == D("700") == row.cash_reserved
    assert row.version >= 2, "deposit bumped the pool epoch"


def test_f1_deposit_epoch_survives_concurrent_admissions(db, tenant, admission_engine):
    get_or_create_admission(db, tenant, "acct-f1", cash=D("1000"))
    db.commit()

    def deposits(_: int) -> None:
        session = sessionmaker(bind=admission_engine, expire_on_commit=False)()
        try:
            for _i in range(5):
                deposit(session, tenant, "acct-f1", D("100"))
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def admission(_: int) -> str:
        session = sessionmaker(bind=admission_engine, expire_on_commit=False)()
        try:
            _admit(session, tenant, key="f1-key-000002", plan_id="plan-f1-b", qty="3")
            session.commit()
            return "admitted"
        except Exception:
            session.rollback()
            return "rejected"
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        deposit_future = pool.submit(deposits, 0)
        admit_future = pool.submit(admission, 1)
        deposit_future.result()
        admission_outcome = admit_future.result()

    db.rollback()
    account = db.get(AccountAdmission, (tenant, "acct-f1"))
    rows = list(
        db.scalars(
            select(ReservationRow).where(
                ReservationRow.tenant_id == tenant,
                ReservationRow.account_id == "acct-f1",
                ReservationRow.state.in_(("HELD", "UNCERTAIN")),
            )
        )
    )
    claims = sum((r.claim for r in rows), D("0"))
    # 5x100 deposits landed; the admission (if it won its race window)
    # reserved 300 without touching available (settlement is the fill's job).
    assert account.cash_available == D("1500")
    expected_reserved = D("300") if admission_outcome == "admitted" else D("0")
    assert account.cash_reserved == claims == expected_reserved
    assert account.cash_reserved <= account.cash_available
    assert account.version >= 6, "epoch advanced once per committed write"


# -- F2 ------------------------------------------------------------------------


def _two_child_plan(*, qty_each: str = "3.57", px: str = "100") -> OrderPlan:
    """A two-child BUY plan whose per-row claims straddle the whole-notional
    rounding boundary (each child notional 357, buffers 15bps)."""
    children = [
        {
            "child_id": f"child-{i:02d}",
            "client_order_id": f"pre-f2-{i:02d}",
            "instrument_id": "KXA8.DEMO",
            "product": "equity",
            "side": "BUY",
            "quantity": {"value": qty_each, "unit": "contracts"},
            "limit_price": {"amount": px, "currency": "USD"},
            "max_notional": {"amount": "100000.00", "currency": "USD"},
        }
        for i in range(2)
    ]
    kwargs = {
        "schema_version": "1.0",
        "plan_id": "plan-f2-boundary",
        "parent_plan_id": None,
        "source_intent_id": "intent-f2-boundary",
        "account_id": "acct-f1",
        "action": "PLACE_ORDER",
        "children": children,
        "risk_policy_revision": "risk-a08-r1",
        "state_snapshot_hash": "b" * 64,
        "max_fee": {"amount": "1.00", "currency": "USD"},
        "max_slippage_bps": D("10"),
        "valid_until": T0,
    }
    draft = OrderPlan.model_construct(
        **{
            **kwargs,
            "action": IntentAction.PLACE_ORDER,
            "children": tuple(ChildOrder(**c) for c in children),
            "max_fee": Money(amount="1.00", currency="USD"),
            "max_slippage_bps": D("10"),
        },
        plan_hash="",
    )
    kwargs["plan_hash"] = canonical_hash(
        draft.model_dump(mode="json", exclude={"plan_hash"})
    )
    return OrderPlan(**kwargs)


def test_f2_multichild_boundary_plan_is_not_spuriously_rejected(db, tenant):
    """Per-child claims 357.00 + 0.54 buffer = 715.08 total vs the policy's
    single-quantized 715.07: sub-cent drift must not reject the plan."""
    from algobots.risk.policy import buffered_reservation

    get_or_create_admission(db, tenant, "acct-f1", cash=D("1000"))
    db.commit()
    policy = make_policy(account="acct-f1", fee_bps="10", slip_bps="5")
    plan = _two_child_plan()
    record_mark(
        db, tenant, "acct-f1", "KXA8.DEMO",
        price=D("100"), currency="USD", quality="REALTIME", observed_at=NOW,
    )
    snapshot = state_snapshot(
        db, tenant, "acct-f1", "KXA8.DEMO", equity_reference=D("1000")
    )
    proposal = make_proposal(account="acct-f1", qty="7.14")
    payload = {"instrument": "KXA8.DEMO", "side": "BUY", "quantity": "7.14"}
    result = admit_entry(
        db, tenant, policy, proposal,
        make_request(key="f2-key-000001", account="acct-f1", payload=payload),
        plan, state=snapshot, now=NOW,
    )
    db.commit()
    # the drift really was sub-cent per row, and admission took the row claims
    assert result.reserved == D("715.08")
    assert buffered_reservation(policy, D("714")) == D("715.07")
    account = db.get(AccountAdmission, (tenant, "acct-f1"))
    assert account.cash_reserved == D("715.08")
    from sqlalchemy import func

    assert db.scalar(
        select(func.count()).select_from(ReservationRow).where(
            ReservationRow.tenant_id == tenant
        )
    ) == 2


def test_f2_tolerance_is_bounded_not_a_shrink_pass(db, tenant):
    """A plan claiming beyond the tolerance (a genuinely stale/oversize plan)
    is still refused: 2 children x 400 = 800 notional vs the 500 cap."""
    get_or_create_admission(db, tenant, "acct-f1", cash=D("1000"))
    db.commit()
    policy = make_policy(account="acct-f1", max_order="500.00")
    plan = _two_child_plan(qty_each="4")
    record_mark(
        db, tenant, "acct-f1", "KXA8.DEMO",
        price=D("100"), currency="USD", quality="REALTIME", observed_at=NOW,
    )
    snapshot = state_snapshot(
        db, tenant, "acct-f1", "KXA8.DEMO", equity_reference=D("1000")
    )
    proposal = make_proposal(account="acct-f1", qty="8")
    payload = {"instrument": "KXA8.DEMO", "side": "BUY", "quantity": "8"}
    with pytest.raises(AdmissionError) as exc:
        admit_entry(
            db, tenant, policy, proposal,
            make_request(key="f2-key-000002", account="acct-f1", payload=payload),
            plan, state=snapshot, now=NOW,
        )
    db.rollback()
    assert "re-plan at the approved size" in str(exc.value)
