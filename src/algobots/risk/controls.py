"""Account risk controls and protective-order validation (A08).

Controls are OPERATOR state, distinct from policy: an operator pauses entries
or authorizes a flatten while the policy document stays frozen. The laws:

- **Pausing entries never removes stops.** An entry pause blocks new risk;
  protective orders (stops, stop-limits, OCO legs) stay working and their
  status stays visible (:func:`protection_status`).
- **Cancel-entries** requests cancellation of working ENTRY orders only —
  never protective or reducing orders.
- **Reduce-only** admits risk-reducing actions exclusively.
- **Flatten is separately authorized**: a flatten cancels everything and
  reduces to zero; it needs its own authorization (recorded actor + expiry)
  and is never implied by a pause.

Protective-order validation (:func:`validate_protective_order`) enforces the
venue constraints the exclusions demand — exits are NOT exempt from venue
constraints: direction must reduce the position it protects, quantity must
not exceed it (no over-hedging into new risk via a "stop"), and the broker's
capabilities must support the protection type for the product.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from algobots.contracts.account import Capabilities, ProtectionOption
from algobots.contracts.enums import OrderSide, OrderType, ProductClass

__all__ = [
    "AccountControls",
    "ControlCheck",
    "ProtectionOrder",
    "ProtectionStatus",
    "check_action",
    "protection_status",
    "validate_protective_order",
]


class ControlAction(StrEnum):
    """The action classes controls dispose of."""

    ENTRY = "ENTRY"
    EXIT = "EXIT"
    REDUCE = "REDUCE"
    PROTECTIVE = "PROTECTIVE"
    CANCEL_ENTRIES = "CANCEL_ENTRIES"
    FLATTEN = "FLATTEN"


class AccountControls(BaseModel):
    """Live operator controls for one account (persisted by admission)."""

    model_config = ConfigDict(extra="forbid")

    entries_paused: bool = False
    cancel_entries_requested: bool = False
    reduce_only: bool = False
    flatten_authorized_by: str | None = None
    flatten_authorized_at: datetime | None = None
    flatten_valid_until: datetime | None = None
    updated_at: datetime | None = None

    def flatten_authorized(self, now: datetime | None = None) -> bool:
        if self.flatten_authorized_by is None or self.flatten_valid_until is None:
            return False
        now = now or datetime.now(UTC)
        return self.flatten_authorized_at <= now <= self.flatten_valid_until


class ControlCheck(BaseModel):
    """Result of checking one action against live controls."""

    model_config = ConfigDict(extra="forbid")

    action: ControlAction
    allowed: bool
    reason: str = ""


def check_action(
    controls: AccountControls, action: ControlAction, *, now: datetime | None = None
) -> ControlCheck:
    """Controls never block risk-reducing actions; flatten needs its grant."""
    if action is ControlAction.FLATTEN:
        if not controls.flatten_authorized(now):
            return ControlCheck(
                action=action,
                allowed=False,
                reason="flatten requires separate authorization (actor + window)",
            )
        return ControlCheck(action=action, allowed=True)
    if action is ControlAction.ENTRY:
        if controls.reduce_only:
            return ControlCheck(
                action=action, allowed=False, reason="account is reduce-only")
        if controls.entries_paused:
            return ControlCheck(
                action=action, allowed=False, reason="entries paused by operator")
    if action is ControlAction.CANCEL_ENTRIES:
        if not controls.cancel_entries_requested:
            return ControlCheck(
                action=action, allowed=False, reason="no cancel-entries request active")
        return ControlCheck(action=action, allowed=True)
    return ControlCheck(action=action, allowed=True)  # EXIT / REDUCE / PROTECTIVE always pass


class ProtectionOrder(BaseModel):
    """A protective order as the venue sees it (working or paused)."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    order_type: OrderType
    protection: ProtectionOption
    side: OrderSide
    quantity: Decimal = Field(gt=0)
    working: bool = True


class ProtectionStatus(BaseModel):
    """What the operator sees after a reconnect: protections, accounted for."""

    model_config = ConfigDict(extra="forbid")

    entries_paused: bool
    reduce_only: bool
    protections: tuple[ProtectionOrder, ...] = ()
    working_protections: int = 0
    paused_protections: int = 0

    @property
    def new_risk_blocked(self) -> bool:
        return self.entries_paused or self.reduce_only


def protection_status(
    controls: AccountControls, protections: tuple[ProtectionOrder, ...]
) -> ProtectionStatus:
    """Entry pause does not remove stops: every protection is listed with its
    working state, so the operator sees what is still defending the book."""
    working = sum(1 for p in protections if p.working)
    return ProtectionStatus(
        entries_paused=controls.entries_paused,
        reduce_only=controls.reduce_only,
        protections=protections,
        working_protections=working,
        paused_protections=len(protections) - working,
    )


class ProtectiveValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    reason: str = ""


def validate_protective_order(
    order: ProtectionOrder,
    *,
    position_quantity: Decimal,
    capabilities: Capabilities,
    product: ProductClass,
) -> ProtectiveValidation:
    """A protective order must REDUCE the position it protects and be
    something the broker actually supports for that product."""

    # 1. Direction: a stop on a long must sell, on a short must buy.
    if position_quantity > 0 and order.side is not OrderSide.SELL:
        return ProtectiveValidation(valid=False, reason="long position requires a SELL protective")
    if position_quantity < 0 and order.side is not OrderSide.BUY:
        return ProtectiveValidation(valid=False, reason="short position requires a BUY protective")
    if position_quantity == 0:
        return ProtectiveValidation(valid=False, reason="no position to protect")

    # 2. Quantity: protecting more than the position is new risk, not protection.
    if order.quantity > abs(position_quantity):
        return ProtectiveValidation(
            valid=False,
            reason=(
                f"protective quantity {order.quantity} exceeds |position| "
                f"{abs(position_quantity)}"
            ),
        )

    # 3. Broker capability: the protection type must be supported (not merely
    #    emulated-unknown); unknown means disabled (contracts.account law).
    if not capabilities.is_enabled(product, order.order_type):
        return ProtectiveValidation(
            valid=False,
            reason=f"broker does not support {order.order_type.value} for {product.value}",
        )
    if order.protection not in _options_for(capabilities, product, order.order_type):
        return ProtectiveValidation(
            valid=False,
            reason=(
                f"broker does not support protection option {order.protection} "
                f"for {product.value}"
            ),
        )
    return ProtectiveValidation(valid=True)


def _options_for(
    capabilities: Capabilities, product: ProductClass, order_type: OrderType
) -> tuple[ProtectionOption, ...]:
    for entry in capabilities.entries:
        if entry.product is product and entry.order_type is order_type:
            return entry.protection_options
    return ()
