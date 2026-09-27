"""Approval queue + append-only action ledger ORM (S4.3, ALG-3092).

Two tables (migration 0004):

- `approval_requests` — one parked would-be-live order awaiting a human
  verdict. State machine: `parked -> approved | rejected | expired`; every
  other transition is illegal (service rejects 4xx, tests prove the matrix).
  Decision rows record actor, verdict reason, and `latency_ms`
  (park -> decision), which also lands in the ledger.
- `action_ledger` — permanent, append-only record of every approval-domain
  action (park, verdict, expiry, broadcast outcome) with reason and latency.
  Immutability is enforced AT THE DATABASE LEVEL (triggers reject UPDATE and
  DELETE — see migration 0004), distinct from the S0.2 middleware `audit_log`
  table, which records HTTP mutations. There is deliberately no `updated_at`
  column: rows are never rewritten.

Broadcast states model what happens when an approved dispatch partially
fills at the venue: `sent` (fully filled), `part_sent` (some filled, nothing
queued), `part_queued` (some filled and/or the remainder queued), `queued`
(fully queued, nothing sent).
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class ApprovalStatus(StrEnum):
    """Human-approval state machine for one parked order."""

    PARKED = "parked"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class BroadcastState(StrEnum):
    """Outcome states of dispatching one approved request to the venue."""

    SENT = "sent"
    PART_SENT = "part_sent"
    PART_QUEUED = "part_queued"
    QUEUED = "queued"


class ApprovalRequest(Base):
    """A parked order awaiting a human verdict (semi-auto mode)."""

    __tablename__ = "approval_requests"
    __table_args__ = (
        Index("ix_approval_requests_user_status", "user_id", "status"),
        Index("ix_approval_requests_user_parked", "user_id", "parked_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    order_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("orders.id"), unique=True, nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id"), nullable=False, index=True
    )
    deployment_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("deployments.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=ApprovalStatus.PARKED.value
    )
    park_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decided_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    decision_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )


class Broadcast(Base):
    """Venue outcome of dispatching one approved request (one row per request)."""

    __tablename__ = "broadcasts"
    __table_args__ = (Index("ix_broadcasts_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    approval_request_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("approval_requests.id"), unique=True, nullable=False, index=True
    )
    total_qty: Mapped[float] = mapped_column(Float, nullable=False)
    sent_qty: Mapped[float] = mapped_column(Float, nullable=False)
    queued_qty: Mapped[float] = mapped_column(Float, nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ActionLedger(Base):
    """Permanent append-only record of one approval-domain action.

    Written for: order parked, verdict recorded, expiry swept, broadcast
    outcome reported. Each row carries the actor, a human-meaningful
    `reason`, and `latency_ms` for the action where a duration applies
    (park -> decision, decision -> broadcast). UPDATE and DELETE are
    rejected by database triggers (migration 0004) — append-only is a DB
    guarantee, not an application promise.
    """

    __tablename__ = "action_ledger"
    __table_args__ = (Index("ix_action_ledger_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_type: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
