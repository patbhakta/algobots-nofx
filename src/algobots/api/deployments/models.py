"""Deployment ORM: frozen strategy snapshots + risk envelope + breaker state.

A deployment is (strategy x symbol x account), frozen at deploy:

- `frozen_spec_json` — the strategy's name/kind/DSL spec captured verbatim at
  deploy time; later strategy edits never reach a running deployment.
- `artifact_hash` — sha256 of the canonical frozen spec; the deployment's
  immutable identity for audit and drift detection.
- `max_order_value` / `max_daily_loss` — the per-deployment risk envelope,
  frozen as decimal strings (money rails never get silent defaults).
- breaker columns — per-deployment breaker (`closed` | `open`); the fleet
  breaker lives in `fleet_breakers` (one row per user) and, when open, halts
  every deployment in that user's scope.

`status` is user intent (`running` | `paused` | `stopped`); halt sources are
tracked separately so fleet resets only resume fleet-halted deployments.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from algobots.api.database import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class DeploymentStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"


# Partial unique backstop: one ACTIVE deployment per (strategy, symbol,
# account). Stopped deployments free the tuple for a fresh deploy.
_ACTIVE_TUPLE_WHERE = text("status <> 'stopped'")


class Deployment(Base):
    """A strategy running against one account for one symbol (frozen at deploy)."""

    __tablename__ = "deployments"
    __table_args__ = (
        Index(
            "uq_deployments_active_tuple",
            "strategy_id",
            "symbol",
            "account_id",
            unique=True,
            sqlite_where=_ACTIVE_TUPLE_WHERE,
            postgresql_where=_ACTIVE_TUPLE_WHERE,
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id"), nullable=False, index=True)
    strategy_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("strategies.id"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("accounts.id"), nullable=False, index=True
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default=DeploymentStatus.RUNNING.value
    )
    frozen_spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    artifact_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    max_order_value: Mapped[str] = mapped_column(String(64), nullable=False)
    max_daily_loss: Mapped[str] = mapped_column(String(64), nullable=False)
    breaker_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BreakerState.CLOSED.value
    )
    breaker_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tripped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )

    @property
    def frozen_spec(self) -> dict:
        """Parsed frozen snapshot (name, kind, spec) for response serialization."""
        import json

        return json.loads(self.frozen_spec_json or "{}")


class FleetBreaker(Base):
    """Fleet-level breaker for one user; `open` halts ALL their deployments."""

    __tablename__ = "fleet_breakers"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id"), unique=True, nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default=BreakerState.CLOSED.value
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tripped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow, nullable=True
    )
