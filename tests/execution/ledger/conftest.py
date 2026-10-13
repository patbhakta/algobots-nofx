"""A07 ledger tests: real-migration SQLite fixture + contract builders.

The DB is provisioned once per session with the real Alembic chain (upgrade
head), matching the control-plane convention: tests exercise migrated schema
and DB-level constraints (append-only triggers, partial unique indexes), never
create_all. Each test uses a fresh tenant id, so the shared file DB never
leaks state between tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from algobots.contracts.plan import (
    ChildOrder,
    IntentRequest,
    OrderPlan,
    Reservation,
    canonical_hash,
)

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)


def ts(seconds: float = 0.0) -> datetime:
    return T0 + timedelta(seconds=seconds)


def make_request(
    *,
    key: str = "key-00000001",
    action: str = "PLACE_ORDER",
    account: str = "acct-main",
    deployment: str | None = "dep-a07",
    payload: dict | None = None,
) -> IntentRequest:
    payload = payload or {"instrument": "KXA7.DEMO", "side": "BUY", "quantity": "10"}
    return IntentRequest(
        schema_version="1.0",
        action=action,
        account_id=account,
        deployment_id=deployment,
        authority_ref="board-directive-2026-10-06",
        idempotency_key=key,
        payload=payload,
        payload_hash=canonical_hash(payload),
    )


def make_plan(
    intent_id,
    *,
    account: str = "acct-main",
    qty: str = "10",
    px: str = "0.50",
    plan_id: str | None = None,
    children: int = 1,
) -> OrderPlan:
    """Build a valid OrderPlan (plan_hash recomputed exactly like the contract)."""
    plan_id = plan_id or f"plan-{str(intent_id)[:8]}"
    child_list = [
        {
            "child_id": f"child-{i:02d}",
            "client_order_id": f"pre-{str(intent_id)[:8]}-{i:02d}",
            "instrument_id": "KXA7.DEMO",
            "product": "equity",
            "side": "BUY",
            "quantity": {"value": qty, "unit": "contracts"},
            "limit_price": {"amount": px, "currency": "USD"},
            "max_notional": {"amount": "100.00", "currency": "USD"},
        }
        for i in range(children)
    ]
    kwargs = {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "parent_plan_id": None,
        "source_intent_id": str(intent_id),
        "account_id": account,
        "action": "PLACE_ORDER",
        "children": child_list,
        "risk_policy_revision": "risk-rev-1",
        "state_snapshot_hash": "a" * 64,
        "max_fee": {"amount": "1.00", "currency": "USD"},
        "max_slippage_bps": Decimal("10"),
        "valid_until": ts(3600),
    }
    from algobots.contracts.base import Money
    from algobots.contracts.enums import IntentAction

    draft = OrderPlan.model_construct(
        **{
            **kwargs,
            "action": IntentAction.PLACE_ORDER,
            "children": tuple(ChildOrder(**c) for c in child_list),
            "max_fee": Money(amount="1.00", currency="USD"),
            "max_slippage_bps": Decimal("10"),
        },
        plan_hash="",
    )
    kwargs["plan_hash"] = canonical_hash(draft.model_dump(mode="json", exclude={"plan_hash"}))
    kwargs["children"] = child_list
    return OrderPlan(**kwargs)


def make_reservation(plan: OrderPlan, *, child_index: int = 0) -> Reservation:
    child = plan.children[child_index]
    qty = child.quantity.value
    return Reservation(
        schema_version="1.0",
        reservation_id=f"resv-{plan.plan_id}-{child.child_id}",
        account_id=plan.account_id,
        instrument_id=child.instrument_id,
        plan_id=plan.plan_id,
        child_id=child.child_id,
        kind="INVENTORY",
        amount={"value": format(qty, "f"), "unit": child.quantity.unit},
        buffer={"value": "0", "unit": child.quantity.unit},
        state="HELD",
        version=0,
    )


@pytest.fixture(scope="session")
def ledger_db_url(tmp_path_factory):
    path = tmp_path_factory.mktemp("a07-ledger") / "ledger.db"
    url = f"sqlite:///{path}"
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield url
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def ledger_engine(ledger_db_url):
    engine = create_engine(ledger_db_url, connect_args={"check_same_thread": False, "timeout": 60})

    @event.listens_for(engine, "connect")
    def _wal(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    yield engine
    engine.dispose()


@pytest.fixture()
def db(ledger_engine) -> Session:
    factory = sessionmaker(bind=ledger_engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def tenant() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture()
def tenant_b() -> uuid.UUID:
    return uuid.uuid4()


def drive_child(
    db, tenant, *, key: str, account: str = "acct-main", faults=(), acknowledge: bool = True
):
    """Common flow: commit -> plan -> stage -> dispatch (-> acknowledge).

    Returns ``(intent_id, child, emulator, outbox)``. With
    ``accept_before_timeout`` the child ends UNKNOWN; with ``connection_drop``
    it stays SUBMITTED and the outbox row stays PENDING.
    """
    from sqlalchemy import select
    from tests.execution.ledger.emulator import BrokerEmulator

    from algobots.execution.ledger import (
        apply_order_event,
        attach_plan,
        commit_intent,
        dispatch_pending,
        stage_commands,
    )
    from algobots.execution.ledger.models import ChildOrder, IntentOutbox

    faults = set(faults)
    intent_id = commit_intent(db, tenant, make_request(key=key, account=account)).intent_id
    plan = make_plan(intent_id, account=account)
    attach_plan(db, tenant, intent_id, plan, [make_reservation(plan)])
    stage_commands(
        db, tenant, intent_id, ownership_epoch=0, policy_revision="risk-rev-1", deadline=ts(300)
    )
    db.commit()
    outbox = db.scalar(select(IntentOutbox).where(IntentOutbox.intent_id == intent_id))
    child = db.scalar(select(ChildOrder).where(ChildOrder.intent_id == intent_id))
    emulator = BrokerEmulator(faults=set(faults))
    dispatch_pending(db, emulator, tenant_id=tenant)
    db.commit()
    db.refresh(child)
    if acknowledge and not (faults & {"accept_before_timeout", "connection_drop"}):
        accepted = emulator.order_event(
            child,
            "ACCEPTED",
            broker_order_id=emulator.broker_order_id(outbox.command_id),
            when=ts(10),
        )
        apply_order_event(db, tenant, accepted)
        db.commit()
        db.refresh(child)
    return intent_id, child, emulator, outbox
