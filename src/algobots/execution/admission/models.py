"""Account admission + reservation store ORM (A08).

All tables live on the control-plane ``Base`` (single Alembic tree, the
db-migrations resource). Money/quantity cross the DB as canonical decimal
strings, same discipline as the A07 ledger.

Serialization law: ``account_admissions`` (and per-instrument
``account_inventories``) rows are the admission serialization points — the
service reserves through a single guarded ``UPDATE`` whose WHERE clause is
the invariant (``reserved + :req <= available``), so concurrent strategies
linearize at the row and the sum of active reservations can never exceed the
permitted funds, whatever the interleaving.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base

__all__ = [
    "ACTIVE_RESERVATION_STATES",
    "AccountAdmission",
    "AccountControlRow",
    "AccountInventory",
    "InstrumentMarkRow",
    "ReservationRow",
]


def _utcnow() -> datetime:
    return datetime.now(UTC)


#: States that still hold a claim on funds/inventory. UNCERTAIN (unknown
#: order, cancel-pending remainder) RETAINS its obligation: it can never fund
#: a new conflicting entry (A08 AC2). CONSUMED settled against the balance;
#: RELEASED returned its claim.
ACTIVE_RESERVATION_STATES = ("HELD", "UNCERTAIN")

RESERVATION_KINDS = ("CASH", "INVENTORY", "MARGIN")


class AccountAdmission(Base):
    """One row per (tenant, account): the account's funds pool and the
    reserved counter the admission UPDATE guards. ``version`` is the
    optimistic epoch bumped on every balance-affecting change."""

    __tablename__ = "account_admissions"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    cash_available_text: Mapped[str] = mapped_column(Text, nullable=False)
    cash_reserved_text: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    @property
    def cash_available(self) -> Decimal:
        return Decimal(self.cash_available_text)

    @property
    def cash_reserved(self) -> Decimal:
        return Decimal(self.cash_reserved_text)


class AccountInventory(Base):
    """One row per (tenant, account, instrument): sellable inventory and its
    reserved counter — a SELL entry reserves inventory the same way a BUY
    reserves cash."""

    __tablename__ = "account_inventories"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    held_text: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    reserved_text: Mapped[str] = mapped_column(Text, nullable=False, default="0")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    @property
    def held(self) -> Decimal:
        return Decimal(self.held_text)

    @property
    def reserved(self) -> Decimal:
        return Decimal(self.reserved_text)


class ReservationRow(Base):
    """One persisted reservation (contract ``Reservation`` @1.0 is its wire
    shape). ``amount`` is the principal claim; ``buffer`` is the fee/slippage
    headroom on top; the funds claim on the account row is both."""

    __tablename__ = "reservations"

    reservation_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False)
    child_id: Mapped[str] = mapped_column(String(128), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    instrument_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str] = mapped_column(String(16), nullable=False)
    amount_text: Mapped[str] = mapped_column(Text, nullable=False)
    buffer_text: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="HELD")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    release_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)

    __table_args__ = (
        Index(
            "uq_reservations_plan_child",
            "tenant_id",
            "plan_id",
            "child_id",
            unique=True,
        ),
        Index(
            "ix_reservations_tenant_account_state",
            "tenant_id",
            "account_id",
            "state",
        ),
    )

    @property
    def amount(self) -> Decimal:
        return Decimal(self.amount_text)

    @property
    def buffer(self) -> Decimal:
        return Decimal(self.buffer_text)

    @property
    def claim(self) -> Decimal:
        """Total funds/inventory claim: amount + buffer."""
        return self.amount + self.buffer


class AccountControlRow(Base):
    """Persisted operator controls (risk.controls.AccountControls is the
    domain shape). Flatten keeps its own actor/expiry columns — separately
    authorized, never implied."""

    __tablename__ = "account_controls"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    entries_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cancel_entries_requested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    reduce_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    flatten_authorized_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    flatten_authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    flatten_valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class InstrumentMarkRow(Base):
    """Last known mark per instrument: price, QUALITY and observation time —
    the stale-state gate consumes exactly this (AC5)."""

    __tablename__ = "instrument_marks"

    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True)
    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    instrument_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    price_text: Mapped[str] = mapped_column(Text, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)
    quality: Mapped[str] = mapped_column(String(16), nullable=False, default="STALE_CACHE")
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    @property
    def price(self) -> Decimal:
        return Decimal(self.price_text)
