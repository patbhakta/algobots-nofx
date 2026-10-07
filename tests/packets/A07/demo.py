"""A07 demo: replay duplicate requests and an accepted-but-timeout order.

Writes artifacts/A07/demo-run.json — the trace evidence for AC1/AC2 (dedup +
guard) and AC3 (UNKNOWN, no blind resubmit, reconciliation finds the original).

    make demo-A07   # or: PYTHONPATH=src python tests/packets/A07/demo.py
"""

from __future__ import annotations

import json
import sys
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from tests.execution.ledger.conftest import (  # noqa: E402
    make_plan,
    make_request,
    make_reservation,
    ts,
)
from tests.execution.ledger.emulator import BrokerEmulator  # noqa: E402

from algobots.execution.ledger import (  # noqa: E402
    GuardRejected,
    apply_events,
    attach_plan,
    commit_intent,
    dispatch_pending,
    get_intent,
    replay_outbox,
    stage_commands,
)
from algobots.execution.ledger.models import ExecutionIntent, IntentOutbox  # noqa: E402

OUT = ROOT / "artifacts" / "A07" / "demo-run.json"


def _fresh_db():
    tmp = tempfile.mkdtemp(prefix="a07-demo-")
    url = f"sqlite:///{tmp}/demo.db"
    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 60})
    return engine


def dedup_replay(engine, tenant: uuid.UUID) -> dict:
    """50 replays of one request (20 concurrently) + 3 same-business requests
    under fresh transport keys: one intent, guard rejections, zero duplicates."""
    request = make_request(key="demo-key-00000001", account="acct-demo")
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def submit_one(_: int):
        session = factory()
        try:
            result = commit_intent(session, tenant, request)
            session.commit()
            return result
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(submit_one, range(20)))
    session = factory()
    for _ in range(30):  # sequential replays on one session
        results.append(commit_intent(session, tenant, request))
    session.commit()

    guard_rejections = 0
    for i in range(3):  # same business signal, different transport keys
        try:
            commit_intent(
                session, tenant, make_request(key=f"demo-key-00000{i + 2}", account="acct-demo")
            )
            session.commit()
        except GuardRejected:
            guard_rejections += 1
            session.rollback()

    intents = session.scalar(
        select(func.count()).select_from(ExecutionIntent).where(ExecutionIntent.tenant_id == tenant)
    )
    return {
        "requests": len(results),
        "intents": intents,
        "created_exactly_once": sum(1 for r in results if r and r.created) == 1,
        "guard_rejections": guard_rejections,
    }


def accept_timeout(engine, tenant: uuid.UUID) -> dict:
    """Accept-before-timeout: UNKNOWN, replay with the stable identity, then
    reconciliation finds the original order and fills it."""
    session = sessionmaker(bind=engine, expire_on_commit=False)()
    trace: list[dict] = []
    intent_id = commit_intent(
        session, tenant, make_request(key="demo-key-00000100", account="acct-demo2")
    ).intent_id
    plan = make_plan(intent_id, account="acct-demo2")
    attach_plan(session, tenant, intent_id, plan, [make_reservation(plan)])
    stage_commands(
        session,
        tenant,
        intent_id,
        ownership_epoch=0,
        policy_revision="risk-rev-1",
        deadline=ts(300),
    )
    session.commit()
    outbox = session.scalar(select(IntentOutbox).where(IntentOutbox.intent_id == intent_id))
    trace.append({"step": "committed+planned+staged", "intent": "SUBMITTED", "outbox": "PENDING"})

    emulator = BrokerEmulator(faults={"accept_before_timeout"})
    report = dispatch_pending(session, emulator, tenant_id=tenant)
    session.commit()
    view = get_intent(session, tenant, intent_id)
    trace.append(
        {
            "step": "submit timed out after broker acceptance",
            "intent": view.status,
            "child": view.orders[0].state,
            "outbox": "PENDING (stable identity retained)",
            "delivered": report.delivered,
            "ambiguous": report.ambiguous,
        }
    )
    broker_order_id = emulator.broker_order_id(outbox.command_id)

    report = replay_outbox(session, emulator, tenant_id=tenant)
    session.commit()
    trace.append(
        {
            "step": "recovery replay of the SAME command",
            "broker_outcome": "DUPLICATE (no second order)",
            "delivered": report.delivered,
            "broker_orders": emulator.order_count,
        }
    )

    child_row = _child_row(session, intent_id)
    reconciliation = [
        emulator.order_event(
            child_row,
            "ACCEPTED",
            broker_order_id=broker_order_id,
            reconciliation=True,
            when=ts(30),
        ),
        emulator.fill_event(
            child_row,
            qty="10",
            broker_order_id=broker_order_id,
            broker_fill_id="demo-fill-1",
            when=ts(31),
        ),
    ]
    apply_events(session, tenant, reconciliation)
    session.commit()
    view = get_intent(session, tenant, intent_id)
    trace.append(
        {
            "step": "reconciliation finds the original",
            "intent": view.status,
            "child": view.orders[0].state,
            "broker_order_id": view.orders[0].broker_order_id,
            "filled": view.orders[0].filled_quantity,
            "fees": view.orders[0].accrued_fees,
        }
    )
    return {
        "trace": trace,
        "final_status": view.status,
        "broker_orders": emulator.order_count,
        "outbox_rows": session.scalar(
            select(func.count()).select_from(IntentOutbox).where(IntentOutbox.tenant_id == tenant)
        ),
    }


def _child_row(session, intent_id):
    from algobots.execution.ledger.models import ChildOrder

    return session.scalar(select(ChildOrder).where(ChildOrder.intent_id == intent_id))


def main() -> int:
    engine = _fresh_db()
    payload = {
        "dedup_replay": dedup_replay(engine, uuid.uuid4()),
        "accept_timeout": accept_timeout(engine, uuid.uuid4()),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
