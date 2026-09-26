"""Control-plane ORM models: multi-tenant, user-scoped stores.

Tables (per ALG-3078): `users`, `invite_codes`, `accounts`, `strategies`,
`deployments`, `orders`, `decisions`, `clamp_events`, `audit_log`.

Tenancy rule: every domain row carries `user_id`; routers always filter by the
authenticated user, so one tenant can never observe or mutate another's rows.
Schema shapes informed by Fincept `broker_accounts` (ALG-3070) and NoFX
user-scoped stores (ALG-3069).
"""

import enum
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_uuid() -> UUID:
    return uuid4()


class UserRole(enum.StrEnum):
    """Founder accounts own invites; members are invited users."""

    OWNER = "owner"
    MEMBER = "member"


class User(Base):
    """A platform tenant principal. Email is unique and stored lowercase."""

    __tablename__ = "users"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default=UserRole.MEMBER.value)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )


class InviteCode(Base):
    """Single-use registration invite created by an authenticated user."""

    __tablename__ = "invite_codes"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=False, index=True
    )
    claimed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id"), nullable=True
    )
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class Account(Base):
    """Broker account owned by a user (paper or live)."""

    __tablename__ = "accounts"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    broker: Mapped[str] = mapped_column(String(64), nullable=False)
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="paper")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    base_currency: Mapped[str] = mapped_column(String(8), nullable=False, default="USD")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )


class Strategy(Base):
    """User-owned strategy definition with free-form parameters."""

    __tablename__ = "strategies"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    params_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )

    @property
    def params(self) -> dict[str, Any]:
        """Parsed view of `params_json` for response serialization."""
        return json.loads(self.params_json or "{}")


class Deployment(Base):
    """A strategy running against an account."""

    __tablename__ = "deployments"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("strategies.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )


class Order(Base):
    """Order routed through a broker account (execution writes these)."""

    __tablename__ = "orders"
    __table_args__ = (Index("ix_orders_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id"), nullable=False, index=True
    )
    deployment_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("deployments.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False, default="market")
    qty: Mapped[float] = mapped_column(Float, nullable=False)
    limit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )


class Decision(Base):
    """Strategy decision record (explainability feed for evals)."""

    __tablename__ = "decisions"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("strategies.id"), nullable=False, index=True
    )
    deployment_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("deployments.id"), nullable=True, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ClampEvent(Base):
    """Risk-clamp application record (exposure caps, kill-switch trips)."""

    __tablename__ = "clamp_events"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    deployment_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("deployments.id"), nullable=True, index=True
    )
    account_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("accounts.id"), nullable=True, index=True
    )
    clamp_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class AuditLog(Base):
    """Immutable record of every mutating request (who/what/where/status).

    Written by the audit middleware for POST/PUT/PATCH/DELETE requests
    regardless of outcome, so failed attempts are auditable too.
    """

    __tablename__ = "audit_log"
    __table_args__ = (Index("ix_audit_log_user_created", "user_id", "created_at"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=_new_uuid)
    user_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True, index=True)
    method: Mapped[str] = mapped_column(String(8), nullable=False)
    path: Mapped[str] = mapped_column(String(512), nullable=False)
    status_code: Mapped[int] = mapped_column(nullable=False)
    resource: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
