"""A08 packet tests: real-migration SQLite fixture + admission builders.

The DB is provisioned once per session with the real Alembic chain (upgrade
head → 0007), the A07 convention: tests exercise migrated schema and
DB-level constraints (CHECKs, unique indexes), never create_all. Each test
uses a fresh tenant id so the shared file DB never leaks state.
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

from algobots.contracts.base import Money
from algobots.contracts.enums import IntentAction
from algobots.contracts.plan import ChildOrder, IntentRequest, OrderPlan, canonical_hash
from algobots.contracts.risk import (
    PolicyConstraints,
    RiskPolicyVersion,
    StaleStateRules,
)
from algobots.risk.policy import RiskProposal

REPO_ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]

T0 = datetime(2026, 10, 7, 12, 0, 0, tzinfo=UTC)
USD = "USD"


def ts(seconds: float = 0.0) -> datetime:
    return T0 + timedelta(seconds=seconds)


def make_policy(
    *,
    account: str = "acct-main",
    max_order: str | None = None,
    max_daily_loss: str | None = None,
    fee_bps: str = "0",
    slip_bps: str = "0",
    revision: str = "risk-a08-r1",
) -> RiskPolicyVersion:
    constraints = PolicyConstraints(
        fee_buffer_bps=Decimal(fee_bps),
        slippage_buffer_bps=Decimal(slip_bps),
    )
    if max_order is not None:
        constraints = constraints.model_copy(
            update={"max_order_notional": Money(amount=max_order, currency=USD)}
        )
    if max_daily_loss is not None:
        constraints = constraints.model_copy(
            update={"max_daily_loss": Money(amount=max_daily_loss, currency=USD)}
        )
    return RiskPolicyVersion(
        schema_version="1.0",
        policy_revision=revision,
        account_id=account,
        base_currency=USD,
        timezone="UTC",
        permissions=(),
        deployment_budgets=(),
        constraints=constraints,
        stale_state=StaleStateRules(
            max_mark_age_seconds=30,
            accepted_mark_qualities=("REALTIME", "DELAYED"),
        ),
        created_at=T0,
    )


def make_proposal(
    *,
    account: str = "acct-main",
    instrument: str = "KXA8.DEMO",
    qty: str = "7",
    px: str = "100",
    kind: str = "ENTRY",
    deployment: str = "dep-1",
) -> RiskProposal:
    from algobots.contracts.enums import OrderSide

    return RiskProposal(
        account_id=account,
        deployment_id=deployment,
        instrument_id=instrument,
        side=OrderSide.BUY if kind == "ENTRY" else OrderSide.SELL,
        kind=kind,
        quantity=Decimal(qty),
        reference_price=Decimal(px),
        currency=USD,
    )


def make_request(
    *,
    key: str = "a08-key-00000001",
    account: str = "acct-main",
    payload: dict | None = None,
) -> IntentRequest:
    payload = payload or {"instrument": "KXA8.DEMO", "side": "BUY", "quantity": "7"}
    return IntentRequest(
        schema_version="1.0",
        action="PLACE_ORDER",
        account_id=account,
        deployment_id="dep-1",
        authority_ref="board-directive-2026-10-06",
        idempotency_key=key,
        payload=payload,
        payload_hash=canonical_hash(payload),
    )


def make_plan(
    *,
    account: str = "acct-main",
    qty: str = "7",
    px: str = "100",
    plan_id: str | None = None,
    instrument: str = "KXA8.DEMO",
) -> OrderPlan:
    """A valid one-child BUY plan (plan_hash recomputed like the contract)."""
    plan_id = plan_id or f"plan-{uuid.uuid4().hex[:10]}"
    child = {
        "child_id": "child-00",
        "client_order_id": f"pre-{plan_id}-00",
        "instrument_id": instrument,
        "product": "equity",
        "side": "BUY",
        "quantity": {"value": qty, "unit": "contracts"},
        "limit_price": {"amount": px, "currency": USD},
        "max_notional": {"amount": "100000.00", "currency": USD},
    }
    kwargs = {
        "schema_version": "1.0",
        "plan_id": plan_id,
        "parent_plan_id": None,
        "source_intent_id": f"intent-{plan_id}",
        "account_id": account,
        "action": "PLACE_ORDER",
        "children": [child],
        "risk_policy_revision": "risk-a08-r1",
        "state_snapshot_hash": "a" * 64,
        "max_fee": {"amount": "1.00", "currency": USD},
        "max_slippage_bps": Decimal("10"),
        "valid_until": ts(3600),
    }
    draft = OrderPlan.model_construct(
        **{
            **kwargs,
            "action": IntentAction.PLACE_ORDER,
            "children": tuple(ChildOrder(**child) for child in [child]),
            "max_fee": Money(amount="1.00", currency=USD),
            "max_slippage_bps": Decimal("10"),
        },
        plan_hash="",
    )
    kwargs["plan_hash"] = canonical_hash(draft.model_dump(mode="json", exclude={"plan_hash"}))
    return OrderPlan(**kwargs)


@pytest.fixture(scope="session")
def admission_db_url(tmp_path_factory):
    path = tmp_path_factory.mktemp("a08-admission") / "admission.db"
    url = f"sqlite:///{path}"
    cfg = Config(str(REPO_ROOT / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.attributes["configure_logger"] = False
    command.upgrade(cfg, "head")
    yield url
    command.downgrade(cfg, "base")


@pytest.fixture(scope="session")
def admission_engine(admission_db_url):
    engine = create_engine(
        url=admission_db_url, connect_args={"check_same_thread": False, "timeout": 60}
    )

    @event.listens_for(engine, "connect")
    def _wal(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA journal_mode=WAL")

    yield engine
    engine.dispose()


@pytest.fixture()
def db(admission_engine) -> Session:
    factory = sessionmaker(bind=admission_engine, expire_on_commit=False)
    session = factory()
    yield session
    session.rollback()
    session.close()


@pytest.fixture()
def tenant() -> uuid.UUID:
    return uuid.uuid4()
