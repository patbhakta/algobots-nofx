"""Intent, order plan, reservation and execution command contracts (roadmap §5)."""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import (
    ContractModel,
    DecimalStr,
    Identifier,
    Money,
    Quantity,
    Sha256Hex,
    UtcDatetime,
    VersionedContract,
)
from .enums import IntentAction, OrderSide

__all__ = [
    "ChildOrder",
    "ExecutionCommand",
    "IntentRequest",
    "OrderPlan",
    "Reservation",
    "canonical_hash",
]


def canonical_hash(payload: Any) -> str:
    """sha256 over canonical JSON (sorted keys, compact separators)."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


@registry.register
class IntentRequest(VersionedContract):
    """``POST /v1/intents`` body. There is no tenant field: the server derives it."""

    contract_name: ClassVar[str] = "IntentRequest"
    contract_version: ClassVar[str] = "1.0"

    action: IntentAction
    account_id: Identifier
    deployment_id: Identifier | None = None
    authority_ref: Identifier
    idempotency_key: Annotated[
        str, Field(min_length=8, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    ]
    payload: dict[str, Any]
    payload_hash: Sha256Hex

    @model_validator(mode="after")
    def _hash_matches(self) -> IntentRequest:
        actual = canonical_hash(self.payload)
        if actual != self.payload_hash:
            raise ValueError(f"payload_hash mismatch (computed {actual[:12]}...)")
        return self


class ChildOrder(ContractModel):
    child_id: Identifier
    client_order_id: Annotated[str, Field(min_length=1, max_length=64)]
    instrument_id: Identifier
    side: OrderSide
    quantity: Quantity
    limit_price: Money | None = None
    max_notional: Money

    @model_validator(mode="after")
    def _positive(self) -> ChildOrder:
        if self.quantity.value <= 0:
            raise ValueError(f"{self.child_id}: quantity must be > 0")
        if self.limit_price is not None and self.limit_price.currency != self.max_notional.currency:
            raise ValueError(f"{self.child_id}: limit_price and max_notional currencies differ")
        return self


@registry.register
class OrderPlan(VersionedContract):
    """Immutable per-account plan. A fan-out parent has one child plan per account
    (linked by ``parent_plan_id``), never one global success flag.
    """

    contract_name: ClassVar[str] = "OrderPlan"
    contract_version: ClassVar[str] = "1.0"

    plan_id: Identifier
    plan_hash: Sha256Hex
    parent_plan_id: Identifier | None = None
    source_intent_id: Identifier
    account_id: Identifier
    children: Annotated[tuple[ChildOrder, ...], Field(min_length=1)]
    risk_policy_revision: Identifier
    state_snapshot_hash: Sha256Hex
    max_fee: Money
    max_slippage_bps: DecimalStr
    valid_until: UtcDatetime

    @model_validator(mode="after")
    def _unique_children(self) -> OrderPlan:
        for attr in ("child_id", "client_order_id"):
            values = [getattr(c, attr) for c in self.children]
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {attr} in plan children")
        if self.max_slippage_bps < 0:
            raise ValueError("max_slippage_bps must be >= 0")
        return self


@registry.register
class Reservation(VersionedContract):
    """Cash/inventory/margin held for one plan child. Uncertain outcomes keep it held."""

    contract_name: ClassVar[str] = "Reservation"
    contract_version: ClassVar[str] = "1.0"

    reservation_id: Identifier
    account_id: Identifier
    instrument_id: Identifier | None = None
    plan_id: Identifier
    child_id: Identifier
    kind: Literal["CASH", "INVENTORY", "MARGIN"]
    amount: Money
    buffer: Money
    state: Literal["HELD", "UNCERTAIN", "CONSUMED", "RELEASED"]
    version: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def _amounts(self) -> Reservation:
        if self.amount.amount <= 0 or self.buffer.amount < 0:
            raise ValueError("reservation amount must be > 0 and buffer >= 0")
        if self.amount.currency != self.buffer.currency:
            raise ValueError("reservation amount and buffer currencies differ")
        return self


@registry.register
class ExecutionCommand(VersionedContract):
    """Only the active fenced sender at ``ownership_epoch`` may submit this."""

    contract_name: ClassVar[str] = "ExecutionCommand"
    contract_version: ClassVar[str] = "1.0"

    command_id: Identifier
    account_id: Identifier
    ownership_epoch: Annotated[int, Field(ge=0)]
    plan_id: Identifier
    plan_hash: Sha256Hex
    policy_revision: Identifier
    deadline: UtcDatetime
    action: IntentAction
