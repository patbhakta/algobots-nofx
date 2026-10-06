"""Broker-observed order and fill events (roadmap §5).

Original broker IDs and raw payload references are preserved; corrections
append (``corrects_*``) and never overwrite. Duplicate-key scope includes the
environment and broker account.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import Identifier, Money, Quantity, UtcDatetime, VersionedContract
from .enums import OrderSide, ProductClass, RuntimeEnvironment

__all__ = ["FillEvent", "OrderEvent", "OrderStatus"]

OrderStatus = Literal[
    "PENDING_SUBMIT",
    "ACCEPTED",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
]


@registry.register
class OrderEvent(VersionedContract):
    contract_name: ClassVar[str] = "OrderEvent"
    contract_version: ClassVar[str] = "1.0"

    event_id: Identifier
    broker_order_id: Identifier | None
    client_order_id: Identifier
    account_id: Identifier
    environment: RuntimeEnvironment
    product: ProductClass
    instrument_id: Identifier
    status: OrderStatus
    quantity: Quantity
    filled_quantity: Quantity
    limit_price: Money | None = None
    event_time: UtcDatetime
    received_time: UtcDatetime
    reconciliation_origin: bool
    corrects_event_id: Identifier | None = None
    raw_payload_ref: Identifier

    @model_validator(mode="after")
    def _fill_bounds(self) -> OrderEvent:
        if self.filled_quantity.unit != self.quantity.unit:
            raise ValueError("filled_quantity and quantity units differ")
        if not 0 <= self.filled_quantity.value <= self.quantity.value:
            raise ValueError("filled_quantity must be within [0, quantity]")
        return self


@registry.register
class FillEvent(VersionedContract):
    """One fill. Brokers without a reliable fill ID supply a qualified composite key."""

    contract_name: ClassVar[str] = "FillEvent"
    contract_version: ClassVar[str] = "1.0"

    fill_id: Identifier
    broker_fill_id: Identifier | None = None
    composite_key: Annotated[str, Field(min_length=1, max_length=256)] | None = None
    broker_order_id: Identifier
    account_id: Identifier
    environment: RuntimeEnvironment
    product: ProductClass
    instrument_id: Identifier
    side: OrderSide
    quantity: Quantity
    price: Money
    fee: Money
    event_time: UtcDatetime
    received_time: UtcDatetime
    reconciliation_origin: bool
    corrects_fill_id: Identifier | None = None
    raw_payload_ref: Identifier

    @model_validator(mode="after")
    def _identity(self) -> FillEvent:
        if (self.broker_fill_id is None) == (self.composite_key is None):
            raise ValueError("set exactly one of broker_fill_id or composite_key")
        if self.quantity.value <= 0:
            raise ValueError("fill quantity must be > 0")
        if self.fee.amount < 0:
            raise ValueError("fee must be >= 0; rebates are separate cash-flow records")
        return self

    @property
    def dedup_key(self) -> tuple[str, str, str]:
        return (
            self.environment.value,
            self.account_id,
            self.broker_fill_id or f"composite:{self.composite_key}",
        )
