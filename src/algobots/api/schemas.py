"""Pydantic request/response schemas for the control-plane API."""

import enum
import json
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    """Base for response models serialized from ORM objects."""

    model_config = ConfigDict(from_attributes=True)


# --- auth ---


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    invite_code: str = Field(min_length=4, max_length=64)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UserOut(ORMModel):
    id: UUID
    email: EmailStr
    display_name: str
    role: str
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class InviteOut(ORMModel):
    id: UUID
    code: str
    claimed_by_user_id: UUID | None
    claimed_at: datetime | None
    expires_at: datetime
    created_at: datetime


# --- accounts ---


class AccountCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    broker: str = Field(min_length=1, max_length=64)
    # `semi_auto` (S4.3): orders on this account park for human approval
    # instead of routing live — paper-only standing law, no live entitlement.
    mode: str = Field(default="paper", pattern="^(paper|live|semi_auto)$")
    base_currency: str = Field(default="USD", min_length=3, max_length=8)


class AccountUpdate(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    mode: str | None = Field(
        default=None, pattern="^(paper|live|semi_auto)$"
    )
    status: str | None = Field(default=None, pattern="^(active|paused|closed)$")


class AccountOut(ORMModel):
    id: UUID
    label: str
    broker: str
    mode: str
    status: str
    base_currency: str
    created_at: datetime
    updated_at: datetime | None


# --- strategies ---


class StrategyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=64)
    params: dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class StrategyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    params: dict[str, Any] | None = None
    is_active: bool | None = None


class StrategyOut(ORMModel):
    id: UUID
    name: str
    kind: str
    params: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime | None


# --- deployments: see algobots.api.deployments.schemas (S4.2) ---


# --- orders ---


class OrderSide(enum.StrEnum):
    buy = "buy"
    sell = "sell"


class OrderCreate(BaseModel):
    account_id: UUID
    deployment_id: UUID | None = None
    symbol: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9./:-]+$")
    side: OrderSide
    order_type: str = Field(default="market", pattern="^(market|limit)$")
    qty: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)


class OrderUpdate(BaseModel):
    status: str = Field(pattern="^(pending|submitted|filled|cancelled|rejected)$")


class OrderOut(ORMModel):
    id: UUID
    account_id: UUID
    deployment_id: UUID | None
    symbol: str
    side: str
    order_type: str
    qty: float
    limit_price: float | None
    status: str
    created_at: datetime
    updated_at: datetime | None


# --- decisions ---


class DecisionCreate(BaseModel):
    strategy_id: UUID
    deployment_id: UUID | None = None
    symbol: str = Field(min_length=1, max_length=32, pattern="^[A-Za-z0-9./:-]+$")
    action: str = Field(pattern="^(buy|sell|hold|close)$")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    rationale: str = Field(default="", max_length=4000)


class DecisionOut(ORMModel):
    id: UUID
    strategy_id: UUID
    deployment_id: UUID | None
    symbol: str
    action: str
    confidence: float
    rationale: str
    created_at: datetime


# --- clamp events ---


class ClampEventCreate(BaseModel):
    deployment_id: UUID | None = None
    account_id: UUID | None = None
    clamp_kind: str = Field(min_length=1, max_length=64)
    old_value: float | None = None
    new_value: float | None = None
    reason: str = Field(default="", max_length=4000)


class ClampEventOut(ORMModel):
    id: UUID
    deployment_id: UUID | None
    account_id: UUID | None
    clamp_kind: str
    old_value: float | None
    new_value: float | None
    reason: str
    created_at: datetime


# --- audit ---


class AuditLogOut(ORMModel):
    id: UUID
    user_id: UUID | None
    method: str
    path: str
    status_code: int
    resource: str
    resource_id: str | None
    detail_json: dict[str, Any]
    created_at: datetime


def params_to_json(params: dict[str, Any]) -> str:
    """Serialize strategy params for storage."""
    return json.dumps(params, sort_keys=True, separators=(",", ":"))
