"""A07 execution-ledger wire contracts: outbox events and the /intents/{id} view.

Both contracts are additive registrations (A07, execution-contract resource):
existing locked name@version entries are untouched. The ledger persists these
shapes; the HTTP mount is A22 scope, which is why the status view lives here
rather than in an api/ schemas module.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import Identifier, UtcDatetime, VersionedContract
from .enums import IntentAction, OrderSide
from .plan import ExecutionCommand

__all__ = ["ChildOrderStatusView", "IntentStatusResponse", "OutboxEvent"]

# Roll-up intent statuses the ledger can report. Values are mirrored by
# algobots.execution.ledger.states.IntentState (alignment is tested).
IntentStatusValue = Literal[
    "ACCEPTED",
    "PLANNED",
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "PENDING_CANCEL",
    "PENDING_REPLACE",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "FAILED",
    "UNKNOWN",
]

ChildOrderStateValue = Literal[
    "SUBMITTED",
    "ACKNOWLEDGED",
    "PARTIALLY_FILLED",
    "PENDING_CANCEL",
    "PENDING_REPLACE",
    "FILLED",
    "CANCELED",
    "REJECTED",
    "EXPIRED",
    "UNKNOWN",
]


@registry.register
class OutboxEvent(VersionedContract):
    """One transactional-outbox message. ``event_id`` is the stable identity:
    recovery replay re-delivers the exact same event (same id, same command),
    and the receiving seam deduplicates on it — replay never mints a new order.
    """

    contract_name: ClassVar[str] = "OutboxEvent"
    contract_version: ClassVar[str] = "1.0"

    event_id: Identifier
    tenant_id: Identifier
    intent_id: Identifier
    plan_id: Identifier
    command: ExecutionCommand
    emitted_at: UtcDatetime

    @model_validator(mode="after")
    def _coherent_refs(self) -> OutboxEvent:
        if self.command.plan_id != self.plan_id:
            raise ValueError("command.plan_id must match the outbox event plan_id")
        return self


class ChildOrderStatusView(VersionedContract):
    """Status of one per-account child order, as reported under /intents/{id}."""

    contract_name: ClassVar[str] = "ChildOrderStatusView"
    contract_version: ClassVar[str] = "1.0"

    child_id: Identifier
    client_order_id: Annotated[str, Field(min_length=1, max_length=64)]
    broker_order_id: Identifier | None = None
    instrument_id: Identifier
    side: OrderSide
    state: ChildOrderStateValue
    quantity: Annotated[str, Field(min_length=1, max_length=64)]
    filled_quantity: Annotated[str, Field(min_length=1, max_length=64)]
    average_fill_price: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    accrued_fees: Annotated[str, Field(min_length=1, max_length=64)]
    currency: Annotated[str, Field(min_length=3, max_length=10)]

    @model_validator(mode="after")
    def _nonnegative(self) -> ChildOrderStatusView:
        from decimal import Decimal

        if Decimal(self.filled_quantity) < 0 or Decimal(self.accrued_fees) < 0:
            raise ValueError("filled_quantity and accrued_fees must be >= 0")
        if Decimal(self.filled_quantity) > Decimal(self.quantity):
            raise ValueError("filled_quantity must be <= quantity")
        return self


@registry.register
class IntentStatusResponse(VersionedContract):
    """``GET /intents/{id}`` body: durable status after the 202 commit."""

    contract_name: ClassVar[str] = "IntentStatusResponse"
    contract_version: ClassVar[str] = "1.0"

    intent_id: Identifier
    idempotency_key: Annotated[str, Field(min_length=8, max_length=128)]
    action: IntentAction
    account_id: Identifier
    payload_hash: Annotated[str, Field(min_length=64, max_length=64)]
    status: IntentStatusValue
    plan_id: Identifier | None = None
    orders: tuple[ChildOrderStatusView, ...] = ()
    account_frozen: bool = False
    created_at: UtcDatetime
    updated_at: UtcDatetime
