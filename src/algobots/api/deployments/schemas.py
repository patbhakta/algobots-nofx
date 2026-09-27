"""Pydantic schemas for deployment create/read/list, breakers, risk reports."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "DailyLossReport",
    "DailyLossReportOut",
    "DeploymentCreate",
    "DeploymentOut",
    "DeploymentUpdate",
    "FleetBreakerAction",
    "FleetBreakerOut",
]


class DeploymentCreate(BaseModel):
    """Deploy (strategy x symbol x account) with a frozen risk envelope.

    The envelope caps are REQUIRED explicit decimals — money rails never get
    silent defaults (see `algobots.risk.envelopes`).
    """

    strategy_id: UUID
    account_id: UUID
    symbol: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9./:-]+$")
    max_order_value: Decimal = Field(gt=0)
    max_daily_loss: Decimal = Field(gt=0)


class DeploymentUpdate(BaseModel):
    """User-intent status change (breaker state is managed by risk routes)."""

    status: Literal["running", "paused", "stopped"]


class DeploymentOut(BaseModel):
    """Secret-free deployment view: frozen snapshot, envelope, breaker state.

    `effective_state` folds status + per-deployment breaker + fleet breaker:
    running | paused | stopped | halted. `halt_source` says which breaker
    halted a running-intent deployment (`deployment_breaker` | `fleet_breaker`).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    strategy_id: UUID
    account_id: UUID
    symbol: str
    status: str
    frozen_spec: dict[str, Any]
    artifact_hash: str
    max_order_value: Decimal
    max_daily_loss: Decimal
    breaker_state: str
    breaker_reason: str
    tripped_at: datetime | None
    effective_state: str
    halt_source: str | None
    created_at: datetime
    updated_at: datetime | None


class DailyLossReport(BaseModel):
    """Signed daily P&L for one deployment (negative is loss)."""

    daily_pnl: Decimal


class DailyLossReportOut(BaseModel):
    """Outcome of checking one report against the FROZEN envelope."""

    deployment_id: UUID
    daily_pnl: Decimal
    max_daily_loss: Decimal
    tripped: bool
    breaker_state: str
    effective_state: str


class FleetBreakerAction(BaseModel):
    """Trip or reset the caller's fleet breaker."""

    action: Literal["trip", "reset"]
    reason: str = Field(default="", max_length=4000)


class FleetBreakerOut(BaseModel):
    """Fleet breaker state for the caller's scope (all their deployments)."""

    model_config = ConfigDict(from_attributes=True)

    state: str
    reason: str
    tripped_at: datetime | None
    updated_at: datetime | None
