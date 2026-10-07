"""Order and intent state machines for the execution ledger (A07).

Legal edges are data, not scattered conditionals, so tests can enumerate the
full transition matrix. Two invariants:

- Terminal states are terminal: no edge leaves ``FILLED/CANCELED/REJECTED/EXPIRED``.
- ``UNKNOWN`` is only exit-able by a reconciliation-origin observation, never
  by a fresh submission — that is the "no blind resubmit" rule (AC3) encoded
  structurally.
"""

from __future__ import annotations

from enum import StrEnum

__all__ = [
    "INTENT_ROLLUP_PRECEDENCE",
    "IntentState",
    "ORDER_ACTIVE_STATES",
    "ORDER_TERMINAL_STATES",
    "OrderState",
    "IllegalTransition",
    "intent_rollup",
    "transition",
]

ENTRY_ACTIONS = frozenset({"CREATE_TARGET", "PLACE_ORDER"})


class OrderState(StrEnum):
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    PENDING_REPLACE = "PENDING_REPLACE"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


class IntentState(StrEnum):
    ACCEPTED = "ACCEPTED"
    PLANNED = "PLANNED"
    SUBMITTED = "SUBMITTED"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    PENDING_CANCEL = "PENDING_CANCEL"
    PENDING_REPLACE = "PENDING_REPLACE"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class IllegalTransition(ValueError):
    """The requested state change is not a legal edge of the state machine."""


_BASE = {
    OrderState.SUBMITTED: frozenset(
        {
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.ACKNOWLEDGED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.PENDING_CANCEL,
            OrderState.PENDING_REPLACE,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PARTIALLY_FILLED: frozenset(
        {
            OrderState.PARTIALLY_FILLED,  # cumulative progress is a legal self-edge
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.EXPIRED,
            OrderState.PENDING_CANCEL,
            OrderState.PENDING_REPLACE,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PENDING_CANCEL: frozenset(
        {
            OrderState.ACKNOWLEDGED,  # cancel rejected: order still live
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,  # fill raced the cancel
            OrderState.CANCELED,
            OrderState.UNKNOWN,
        }
    ),
    OrderState.PENDING_REPLACE: frozenset(
        {
            OrderState.ACKNOWLEDGED,  # replace rejected
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,  # replaced: original cancelled, successor is a new child
            OrderState.UNKNOWN,
        }
    ),
    # UNKNOWN is only exit-able via reconciliation_origin observations.
    OrderState.UNKNOWN: frozenset(
        {
            OrderState.ACKNOWLEDGED,
            OrderState.PARTIALLY_FILLED,
            OrderState.FILLED,
            OrderState.CANCELED,
            OrderState.REJECTED,
            OrderState.EXPIRED,
        }
    ),
    OrderState.FILLED: frozenset(),
    OrderState.CANCELED: frozenset(),
    OrderState.REJECTED: frozenset(),
    OrderState.EXPIRED: frozenset(),
}

ORDER_TERMINAL_STATES = frozenset(
    {OrderState.FILLED, OrderState.CANCELED, OrderState.REJECTED, OrderState.EXPIRED}
)
ORDER_ACTIVE_STATES = frozenset(set(OrderState) - ORDER_TERMINAL_STATES)

_LEGAL = dict(_BASE)

# OrderEvent.status (contract vocabulary) -> ledger OrderState. The contract
# says ACCEPTED where the ledger state machine says ACKNOWLEDGED (an accepted
# order is one the broker has acknowledged).
EVENT_STATUS_TO_STATE: dict[str, OrderState] = {
    "PENDING_SUBMIT": OrderState.SUBMITTED,
    "ACCEPTED": OrderState.ACKNOWLEDGED,
    "PARTIALLY_FILLED": OrderState.PARTIALLY_FILLED,
    "FILLED": OrderState.FILLED,
    "CANCELED": OrderState.CANCELED,
    "REJECTED": OrderState.REJECTED,
    "EXPIRED": OrderState.EXPIRED,
    "UNKNOWN": OrderState.UNKNOWN,
}


def transition(
    current: OrderState, target: OrderState, *, reconciliation: bool = False
) -> OrderState:
    """Return ``target`` if the edge is legal, else raise :class:`IllegalTransition`.

    Leaving ``UNKNOWN`` requires ``reconciliation=True`` (the observation must
    originate from a reconciliation pass, not from a fresh submission).
    """
    if current == target:
        return target
    if target not in _LEGAL[current]:
        raise IllegalTransition(f"{current.value} -> {target.value} is not a legal edge")
    if current is OrderState.UNKNOWN and not reconciliation:
        raise IllegalTransition(
            f"{current.value} -> {target.value} requires a reconciliation-origin observation "
            "(no blind resubmit)"
        )
    return target


# Intent roll-up: given the multiset of child states, the intent reports the
# most consequential state. Order matters: first match wins.
INTENT_ROLLUP_PRECEDENCE: tuple[OrderState, ...] = (
    OrderState.UNKNOWN,
    OrderState.SUBMITTED,
    OrderState.PENDING_REPLACE,
    OrderState.PENDING_CANCEL,
    OrderState.PARTIALLY_FILLED,
    OrderState.ACKNOWLEDGED,
)


def intent_rollup(child_states: list[OrderState], *, planned: bool) -> IntentState:
    """Aggregate child order states into the intent status."""
    if not child_states:
        return IntentState.PLANNED if planned else IntentState.ACCEPTED
    states = set(child_states)
    if states <= {OrderState.FILLED}:
        return IntentState.FILLED
    for candidate in INTENT_ROLLUP_PRECEDENCE:
        if candidate in states:
            return IntentState(candidate.value)
    if states <= {OrderState.CANCELED}:
        return IntentState.CANCELED
    if states <= {OrderState.REJECTED}:
        return IntentState.REJECTED
    if states <= {OrderState.EXPIRED}:
        return IntentState.EXPIRED
    # Mixed terminal outcomes (e.g. one filled, one canceled): FAILED.
    if states <= ORDER_TERMINAL_STATES:
        return IntentState.FAILED
    raise AssertionError(f"unreachable rollup for {states}")
