"""Pydantic schemas for the approval queue and action ledger (S4.3)."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ApprovalDecide",
    "ApprovalOut",
    "BroadcastOut",
    "BroadcastReport",
    "ExpirySweepOut",
    "LedgerOut",
]


class ApprovalDecide(BaseModel):
    """Human verdict on one parked request.

    `reason` is REQUIRED on reject (a rejection without a recorded reason is
    a 422); on approve it is optional context.
    """

    verdict: Literal["approved", "rejected"]
    reason: str = Field(default="", max_length=4000)


class ApprovalOut(BaseModel):
    """Secret-free view of one approval request with decision latency."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    account_id: UUID
    deployment_id: UUID | None
    symbol: str
    side: str
    order_type: str
    qty: float
    limit_price: float | None
    status: str
    park_reason: str
    decided_by: UUID | None
    decision_reason: str
    latency_ms: int | None
    parked_at: datetime
    decided_at: datetime | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime | None
    broadcast: "BroadcastOut | None" = None


class BroadcastReport(BaseModel):
    """Venue outcome of dispatching an approved request.

    `sent_qty` is the portion filled/executed at the venue; `queued_qty` the
    portion left queued (not executed). Their sum may not exceed the
    request's order quantity.
    """

    sent_qty: float = Field(ge=0)
    queued_qty: float = Field(ge=0)
    reason: str = Field(default="", max_length=4000)


class BroadcastOut(BaseModel):
    """Computed part-sent / part-queued state for one approved dispatch."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    approval_request_id: UUID
    total_qty: float
    sent_qty: float
    queued_qty: float
    state: str
    reason: str
    latency_ms: int | None
    created_at: datetime


class ExpirySweepOut(BaseModel):
    """Result of sweeping overdue parked requests to `expired`."""

    expired: int


class LedgerOut(BaseModel):
    """One append-only action-ledger row (actor, reason, latency)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    action: str
    subject_type: str
    subject_id: UUID
    actor_id: UUID | None
    reason: str
    latency_ms: int | None
    detail_json: dict[str, Any]
    created_at: datetime
