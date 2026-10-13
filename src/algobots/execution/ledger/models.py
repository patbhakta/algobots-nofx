"""Durable ledger ORM (A07). All tables live on the control-plane ``Base`` so
the single Alembic tree owns them; tenancy is a plain column (the API derives
it, the ledger never trusts a client-supplied tenant).

Money/quantity cross the DB as canonical decimal strings in ``*_text`` columns
(same discipline as the contracts: no floats in a ledger). JSON payloads are
``*_json`` Text columns with sorted-key compact encoding.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base

__all__ = [
    "ACCOUNT_FREEZE_REASON_MAX",
    "AccountFreeze",
    "CashMovement",
    "ChildOrder",
    "FillReceipt",
    "IntentOutbox",
    "OrderEventReceipt",
    "OrderPlanRow",
    "ACTIVE_ENTRY_STATUSES",
    "ExecutionIntent",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _d(value: str | Decimal) -> str:
    return format(value, "f") if isinstance(value, Decimal) else value


ACTIVE_ENTRY_STATUSES = (
    "ACCEPTED",
    "PLANNED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "PENDING_CANCEL",
    "PENDING_REPLACE",
    "UNKNOWN",
)

# The guard protects ENTRIES only: cancels/reduces/flattens with the same
# business shape must stay admissible (they are exits, not duplicates).
ENTRY_ACTION_VALUES = ("CREATE_TARGET", "PLACE_ORDER")

_ACTIVE_ENTRY_WHERE = Text(
    "status IN (" + ", ".join(f"'{s}'" for s in ACTIVE_ENTRY_STATUSES) + ")"
    " AND action IN (" + ", ".join(f"'{a}'" for a in ENTRY_ACTION_VALUES) + ")"
)

ACCOUNT_FREEZE_REASON_MAX = 32


class ExecutionIntent(Base):
    """A durably committed intent. Unique (tenant, idempotency_key) is the
    transport-key dedup; the partial unique (tenant, account, business_hash)
    over active statuses is the active-entry guard against repeated business
    signals that arrive with different transport keys.
    """

    __tablename__ = "execution_intents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    deployment_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    authority_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    business_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACCEPTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index(
            "uq_execution_intents_tenant_idem",
            "tenant_id",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "uq_execution_intents_active_entry",
            "tenant_id",
            "account_id",
            "business_hash",
            unique=True,
            sqlite_where=_ACTIVE_ENTRY_WHERE,
            postgresql_where=_ACTIVE_ENTRY_WHERE,
        ),
        Index(
            "ix_execution_intents_tenant_account_status",
            "tenant_id",
            "account_id",
            "status",
        ),
    )


class OrderPlanRow(Base):
    """Immutable persisted OrderPlan + its reservations ("preserve unresolved
    commands and reservations" across recovery).
    """

    __tablename__ = "order_plans"

    plan_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("execution_intents.id"), nullable=False, index=True
    )
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    plan_json: Mapped[str] = mapped_column(Text, nullable=False)
    reservations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ChildOrder(Base):
    """One per-account child order with its own client order ID. Cumulative
    fill/fee columns are event projections recomputed idempotently from the
    append-only receipt log.
    """

    __tablename__ = "child_orders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("execution_intents.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(
        String(128), ForeignKey("order_plans.plan_id"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    child_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_order_id: Mapped[str] = mapped_column(String(64), nullable=False)
    broker_order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    instrument_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity_text: Mapped[str] = mapped_column(Text, nullable=False)
    limit_price_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    max_notional_text: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="SUBMITTED")
    filled_qty_text: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    avg_px_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    fees_text: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (
        Index(
            "uq_child_orders_tenant_account_client_id",
            "tenant_id",
            "account_id",
            "client_order_id",
            unique=True,
        ),
        Index(
            "uq_child_orders_tenant_account_broker_id",
            "tenant_id",
            "account_id",
            "broker_order_id",
            unique=True,
        ),
        Index("uq_child_orders_intent_child", "intent_id", "child_id", unique=True),
    )

    # Decimal accessors keep float out of ledger math.
    @property
    def quantity(self) -> Decimal:
        return Decimal(self.quantity_text)

    @property
    def filled_qty(self) -> Decimal:
        return Decimal(self.filled_qty_text)

    @property
    def fees(self) -> Decimal:
        return Decimal(self.fees_text)


class OrderEventReceipt(Base):
    """Dedup record for a delivered OrderEvent. Append-only (DB triggers)."""

    __tablename__ = "order_event_receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False)
    child_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("child_orders.id"), nullable=True, index=True
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    reconciliation_origin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    event_json: Mapped[str] = mapped_column(Text, nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("uq_order_event_receipts_dedup", "dedup_key", unique=True),)


class FillReceipt(Base):
    """Dedup record for one FillEvent (AC4: exactly-once settlement). Append-only."""

    __tablename__ = "fill_receipts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(256), nullable=False)
    child_order_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), ForeignKey("child_orders.id"), nullable=True, index=True
    )
    fill_id: Mapped[str] = mapped_column(String(128), nullable=False)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity_text: Mapped[str] = mapped_column(Text, nullable=False)
    price_text: Mapped[str] = mapped_column(Text, nullable=False)
    fee_text: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    corrects_fill_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    received_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("uq_fill_receipts_dedup", "dedup_key", unique=True),)


class CashMovement(Base):
    """Idempotent settlement entry: one row per (cause, kind), enforced by the
    unique movement_key. Append-only.

    Signs: FILL_NOTIONAL is signed by side (BUY negative cash, SELL positive);
    FEE is always negative; CORRECTION carries its own sign.
    """

    __tablename__ = "cash_movements"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    movement_key: Mapped[str] = mapped_column(String(256), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_text: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    ref_type: Mapped[str] = mapped_column(String(16), nullable=False)
    ref_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    __table_args__ = (Index("uq_cash_movements_key", "movement_key", unique=True),)


class IntentOutbox(Base):
    """Transactional outbox. ``event_id`` is the stable identity: recovery
    replay re-delivers the same row; the seam deduplicates on it.
    """

    __tablename__ = "intent_outbox"

    event_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    intent_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("execution_intents.id"), nullable=False, index=True
    )
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    child_order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("child_orders.id"), nullable=False, index=True
    )
    command_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False, default="EXECUTION_COMMAND")
    command_json: Mapped[str] = mapped_column(Text, nullable=False)
    emitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_intent_outbox_status_created", "status", "created_at"),)


class AccountFreeze(Base):
    """Account frozen on ambiguous order existence (AC5). One active freeze
    per (tenant, account) until an operator resolution closes it.
    """

    __tablename__ = "account_freezes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(ACCOUNT_FREEZE_REASON_MAX), nullable=False)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index(
            "uq_account_freezes_active",
            "tenant_id",
            "account_id",
            unique=True,
            sqlite_where=Text("resolved_at IS NULL"),
            postgresql_where=Text("resolved_at IS NULL"),
        ),
    )
