"""A08 demo: race two strategies for shared funds; entry pause keeps stops.

Writes artifacts/A08/demo-run.json — the packet's required demo evidence:

1. RACE — a $1,000 shared pool, two strategies each trying to admit a $700
   entry concurrently (separate sessions, real threads). Exactly one wins;
   the loser is rejected with the funds rule; the pool invariant
   (reserved == sum of active claims <= available) holds throughout.
2. PAUSE — the operator pauses entries mid-flight: the next entry is denied
   (account_control), the working stop stays working, and the protection
   status shows it. Releasing the pause re-admits entries.
3. STALE — a stale mark blocks new risk (stale_state) with protections
   still visible; a fresh mark unblocks it.

    PYTHONPATH=src python tests/packets/A08/demo.py
"""

from __future__ import annotations

import json
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import sessionmaker

from algobots.api.database import Base  # noqa: F401 — register models
from algobots.contracts.enums import OrderSide, OrderType
from algobots.execution.admission import (
    AdmissionDenied,
    OvercommitRejected,
    admit_entry,
    get_controls,
    get_or_create_admission,
    record_mark,
    release_reservation,
    set_controls,
    state_snapshot,
)
from algobots.execution.admission.models import AccountAdmission, ReservationRow
from algobots.risk.controls import AccountControls, ProtectionOrder, protection_status

sys.path.insert(0, str(Path(__file__).resolve().parent))
from conftest import (  # noqa: E402
    T0,
    make_plan,
    make_policy,
    make_proposal,
    make_request,
)

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A08" / "demo-run.json"
D = Decimal
ACCOUNT = "acct-demo"
INSTRUMENTS = ("KXA8.DEMO", "KXB8.DEMO")
STOPS = (
    ProtectionOrder(
        instrument_id="KXA8.DEMO",
        order_type=OrderType.STOP,
        protection="stop",
        side=OrderSide.SELL,
        quantity=D("7"),
        working=True,
    ),
)


def provision(url: str):
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    return cfg


def attempt(session, tenant, policy, *, instrument: str, slot: int) -> dict:
    record_mark(
        session, tenant, ACCOUNT, instrument,
        price=D("100"), currency="USD", quality="REALTIME", observed_at=T0,
    )
    snapshot = state_snapshot(session, tenant, ACCOUNT, instrument, equity_reference=D("1000"))
    payload = {"instrument": instrument, "side": "BUY", "quantity": "7"}
    try:
        result = admit_entry(
            session, tenant, policy,
            make_proposal(account=ACCOUNT, instrument=instrument),
            make_request(key=f"demo-race-{slot}", account=ACCOUNT, payload=payload),
            make_plan(account=ACCOUNT, plan_id=f"plan-demo-{slot}", instrument=instrument),
            state=snapshot, now=T0,
        )
        session.commit()
        return {"strategy": slot, "outcome": "ADMITTED", "reserved": str(result.reserved)}
    except (AdmissionDenied, OvercommitRejected) as exc:
        session.rollback()
        detail = getattr(exc, "decision", None)
        return {
            "strategy": slot,
            "outcome": "REJECTED",
            "rule": detail.rule if detail else "insufficient_funds",
            "reason": detail.reason if detail else str(exc),
        }


def _dump(model) -> dict:
    return json.loads(model.model_dump_json())


def pool_state(session, tenant) -> dict:
    account = session.get(AccountAdmission, (tenant, ACCOUNT))
    claims = list(
        session.scalars(
            select(ReservationRow).where(
                ReservationRow.tenant_id == tenant,
                ReservationRow.account_id == ACCOUNT,
                ReservationRow.state.in_(("HELD", "UNCERTAIN")),
            )
        )
    )
    total = sum((r.claim for r in claims), D("0"))
    return {
        "available": str(account.cash_available),
        "reserved": str(account.cash_reserved),
        "active_claims": str(total),
        "invariant_holds": account.cash_reserved == total <= account.cash_available,
        "active_reservations": [
            {"plan": r.plan_id, "state": r.state, "claim": str(r.claim)}
            for r in sorted(claims, key=lambda r: r.plan_id)
        ],
    }


def main() -> int:
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        url = f"sqlite:///{tmp}/a08-demo.db"
        provision(url)
        engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60})

        @event.listens_for(engine, "connect")
        def _wal(dbapi_connection, _record):
            dbapi_connection.execute("PRAGMA journal_mode=WAL")

        factory = sessionmaker(bind=engine, expire_on_commit=False)
        tenant = uuid.uuid4()
        policy = make_policy(account=ACCOUNT)

        # -- 1. the race ----------------------------------------------------
        session = factory()
        get_or_create_admission(session, tenant, ACCOUNT, cash=D("1000"))
        session.commit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            race = list(
                pool.map(
                    lambda slot: attempt(
                        factory(), tenant, policy, instrument=INSTRUMENTS[slot], slot=slot
                    ),
                    range(2),
                )
            )
        race.sort(key=lambda r: r["strategy"])
        after_race = pool_state(session, tenant)

        # the race winner's order is reconciled-rejected: funds return (this
        # is also what makes the pause scenario run against a full pool)
        winner_rows = list(
            session.scalars(
                select(ReservationRow).where(
                    ReservationRow.tenant_id == tenant,
                    ReservationRow.account_id == ACCOUNT,
                    ReservationRow.state.in_(("HELD", "UNCERTAIN")),
                )
            )
        )
        for row in winner_rows:
            release_reservation(session, tenant, row.reservation_id, "RECONCILED_REJECTION")
        session.commit()
        after_race_release = pool_state(session, tenant)

        # -- 2. entry pause without removing stops ---------------------------
        set_controls(session, tenant, ACCOUNT, AccountControls(entries_paused=True))
        session.commit()
        paused_entry = attempt(factory(), tenant, policy, instrument="KXC8.DEMO", slot=2)
        status_while_paused = protection_status(get_controls(session, tenant, ACCOUNT), STOPS)

        set_controls(session, tenant, ACCOUNT, AccountControls(entries_paused=False))
        session.commit()
        resumed_entry = attempt(factory(), tenant, policy, instrument="KXC8.DEMO", slot=3)
        if resumed_entry["outcome"] == "ADMITTED":
            # hand the pool back before the staleness scenario (reconciled)
            row = session.scalar(
                select(ReservationRow).where(
                    ReservationRow.tenant_id == tenant,
                    ReservationRow.plan_id == "plan-demo-3",
                )
            )
            release_reservation(session, tenant, row.reservation_id, "RECONCILED_REJECTION")
            session.commit()

        # -- 3. stale mark blocks new risk; fresh unblocks --------------------
        stale_time = T0 - timedelta(seconds=120)
        record_mark(
            session, tenant, ACCOUNT, "KXD8.DEMO",
            price=D("100"), currency="USD", quality="STALE_CACHE", observed_at=stale_time,
        )
        stale_snapshot = state_snapshot(
            session, tenant, ACCOUNT, "KXD8.DEMO", equity_reference=D("1000")
        )
        try:
            admit_entry(
                session, tenant, policy,
                make_proposal(account=ACCOUNT, instrument="KXD8.DEMO"),
                make_request(key="demo-stale-1", account=ACCOUNT,
                             payload={"instrument": "KXD8.DEMO", "side": "BUY", "quantity": "7"}),
                make_plan(account=ACCOUNT, plan_id="plan-demo-stale", instrument="KXD8.DEMO"),
                state=stale_snapshot, now=T0,
            )
            session.commit()
            stale_outcome = {"outcome": "ADMITTED", "problem": "stale state was NOT enforced"}
        except AdmissionDenied as exc:
            session.rollback()
            stale_outcome = {
                "outcome": "REJECTED",
                "rule": exc.decision.rule,
                "reason": exc.decision.reason,
            }
        status_while_stale = protection_status(get_controls(session, tenant, ACCOUNT), STOPS)

        record_mark(
            session, tenant, ACCOUNT, "KXD8.DEMO",
            price=D("100"), currency="USD", quality="REALTIME", observed_at=T0,
        )
        fresh_snapshot = state_snapshot(
            session, tenant, ACCOUNT, "KXD8.DEMO", equity_reference=D("1000")
        )
        fresh = admit_entry(
            session, tenant, policy,
            make_proposal(account=ACCOUNT, instrument="KXD8.DEMO"),
            make_request(key="demo-stale-2", account=ACCOUNT,
                         payload={"instrument": "KXD8.DEMO", "side": "BUY", "quantity": "7"}),
            make_plan(account=ACCOUNT, plan_id="plan-demo-fresh", instrument="KXD8.DEMO"),
            state=fresh_snapshot, now=T0,
        )
        session.commit()
        final = pool_state(session, tenant)

        # release what we hold, prove funds return (recovery posture)
        rows = list(
            session.scalars(
                select(ReservationRow).where(
                    ReservationRow.tenant_id == tenant,
                    ReservationRow.account_id == ACCOUNT,
                    ReservationRow.state.in_(("HELD", "UNCERTAIN")),
                )
            )
        )
        for row in rows:
            release_reservation(session, tenant, row.reservation_id, "RECONCILED_REJECTION")
        session.commit()
        after_release = pool_state(session, tenant)
        session.close()
        engine.dispose()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "packet": "A08",
                "generated_at": datetime.now(UTC).isoformat(),
                "scenario_1_race_for_shared_funds": {
                    "pool": "1000",
                    "entries": ["700 (KXA8.DEMO)", "700 (KXB8.DEMO)"],
                    "outcomes": race,
                    "after_race": after_race,
                    "after_reconciled_release": after_race_release,
                    "exactly_one_admitted": sum(
                        1 for r in race if r["outcome"] == "ADMITTED"
                    )
                    == 1,
                },
                "scenario_2_entry_pause_keeps_stops": {
                    "entry_while_paused": paused_entry,
                    "protection_status_while_paused": _dump(status_while_paused),
                    "entry_after_resume": resumed_entry,
                },
                "scenario_3_stale_state_blocks_new_risk": {
                    "stale_entry": stale_outcome,
                    "protection_status_while_stale": _dump(status_while_stale),
                    "fresh_entry": {
                        "outcome": "ADMITTED",
                        "reserved": str(fresh.reserved),
                    },
                },
                "final_pool": final,
                "after_reconciled_release": after_release,
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(race, indent=1))
    print(f"demo evidence -> {OUT.relative_to(ROOT)}")
    ok = (
        sum(1 for r in race if r["outcome"] == "ADMITTED") == 1
        and after_race["invariant_holds"]
        and paused_entry["outcome"] == "REJECTED"
        and status_while_paused.working_protections == 1
        and stale_outcome["rule"] == "stale_state"
        and D(after_release["reserved"]) == 0
        and resumed_entry["outcome"] == "ADMITTED"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
