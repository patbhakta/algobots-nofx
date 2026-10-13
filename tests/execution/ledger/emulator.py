"""Broker fault emulator — the A07 ExecutionClient-seam test double.

Per the spine constraint (ADR 0001) the ledger only ever sees
``OrderEvent``/``FillEvent`` contracts; this emulator plays the seam in
tests and derives exactly those shapes. It never bypasses the event path.

Scriptable faults (the packet's list, driving AC3-AC5):

- ``accept_before_timeout``  submit is accepted broker-side, then the
  response times out -> :class:`AmbiguousSubmit` (existence resolvable via
  client-ID lookup once the broker answers).
- ``connection_drop``        the connection dies before delivery; the
  command was NOT registered (unambiguous "never landed").
- ``no_client_id_lookup``    combined with an ambiguous submit: the broker
  cannot answer a client-order-ID lookup, so existence stays ambiguous
  (AC5's freeze condition).
- ``duplicate_fill`` / ``reordered_events`` / ``delayed_cancel``   event
  stream shapes produced by the script helpers below.

Dedup contract of the emulator: a replayed command (same ``command_id``) is
acknowledged as ``DUPLICATE`` and NEVER registers a second broker order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from algobots.contracts.events import FillEvent, OrderEvent
from algobots.contracts.outbox import OutboxEvent
from algobots.execution.ledger.errors import AmbiguousSubmit

FAULTS = (
    "accept_before_timeout",
    "connection_drop",
    "no_client_id_lookup",
    "duplicate_fill",
    "reordered_events",
    "delayed_cancel",
)


@dataclass
class BrokerEmulator:
    """Callable sink for ``dispatch_pending`` plus event script helpers."""

    faults: set[str] = field(default_factory=set)
    # command_id -> broker_order_id (what the broker side actually holds)
    orders: dict[str, str] = field(default_factory=dict)
    # every submit call: (outbox event_id, command_id, outcome)
    submit_log: list[tuple[str, str, str]] = field(default_factory=list)
    _seq: int = 0

    def __call__(self, event: OutboxEvent) -> str:
        return self.submit(event)

    # -- sink ---------------------------------------------------------------

    def submit(self, event: OutboxEvent) -> str:
        command_id = event.command.command_id
        if command_id in self.orders:  # stable-identity replay: never a second order
            outcome = "DUPLICATE"
            self.submit_log.append((event.event_id, command_id, outcome))
            return outcome
        if "connection_drop" in self.faults:
            self.submit_log.append((event.event_id, command_id, "DROP"))
            raise ConnectionError("seam connection dropped before delivery")
        if "accept_before_timeout" in self.faults:
            self._register(command_id)  # the broker DID accept...
            self.submit_log.append((event.event_id, command_id, "TIMEOUT_AFTER_ACCEPT"))
            raise AmbiguousSubmit(
                "submit timed out after broker acceptance",
                lookup_available="no_client_id_lookup" not in self.faults,
            )
        self._register(command_id)
        outcome = "ACCEPTED"
        self.submit_log.append((event.event_id, command_id, outcome))
        return outcome

    def _register(self, command_id: str) -> None:
        self._seq += 1
        self.orders[command_id] = f"BRK-{self._seq:06d}"

    @property
    def order_count(self) -> int:
        return len(self.orders)

    # -- event scripts (engine-derived shapes only) --------------------------

    def broker_order_id(self, command_id: str) -> str:
        return self.orders[command_id]

    def order_event(
        self,
        child,
        status: str,
        *,
        broker_order_id: str | None = None,
        filled_qty: str | None = None,
        reconciliation: bool = False,
        event_id: str | None = None,
        when: datetime,
    ) -> OrderEvent:
        """Derive an OrderEvent for a child order (``child`` = ledger ChildOrder)."""
        self._seq += 1
        event_id = event_id or f"oe-{self._seq:06d}"
        filled = filled_qty if filled_qty is not None else child.filled_qty_text
        return OrderEvent(
            schema_version="1.0",
            event_id=event_id,
            broker_order_id=broker_order_id or child.broker_order_id,
            client_order_id=child.client_order_id,
            account_id=child.account_id,
            environment="synthetic-paper",
            product=child.product,
            instrument_id=child.instrument_id,
            status=status,
            quantity={"value": child.quantity_text, "unit": "contracts"},
            filled_quantity={"value": filled, "unit": "contracts"},
            event_time=when,
            received_time=when,
            reconciliation_origin=reconciliation,
            raw_payload_ref=f"raw://{event_id}",
        )

    def fill_event(
        self,
        child,
        *,
        qty: str,
        px: str = "0.50",
        fee: str = "0.07",
        broker_order_id: str | None = None,
        broker_fill_id: str | None = None,
        composite_key: str | None = None,
        reconciliation: bool = False,
        when: datetime,
    ) -> FillEvent:
        """Derive a FillEvent for a child order (from a Nautilus OrderFilled).

        ``broker_order_id`` overrides the child's (possibly not yet learned)
        mapping — the broker side always knows its own id, our ledger may not
        have seen the acceptance yet (reordered delivery).
        """
        self._seq += 1
        seq = self._seq
        if broker_fill_id is None and composite_key is None:
            composite_key = f"emulator:{seq}"
        fill_id = broker_fill_id or f"fill-{seq:06d}"
        return FillEvent(
            schema_version="1.0",
            fill_id=fill_id,
            broker_fill_id=broker_fill_id,
            composite_key=composite_key,
            broker_order_id=broker_order_id or child.broker_order_id,
            account_id=child.account_id,
            environment="synthetic-paper",
            product=child.product,
            instrument_id=child.instrument_id,
            side=child.side,
            quantity={"value": qty, "unit": "contracts"},
            price={"amount": px, "currency": "USD"},
            fee={"amount": fee, "currency": "USD"},
            event_time=when,
            received_time=when,
            reconciliation_origin=reconciliation,
            raw_payload_ref=f"raw://{fill_id}",
        )

    # -- fault-shaped stream helpers -----------------------------------------

    def duplicate_fill_stream(self, child, *, when: datetime) -> list[FillEvent]:
        """The same fill delivered twice (broker redelivery)."""
        fill = self.fill_event(
            child, qty="4", px="0.50", fee="0.14", broker_fill_id="dup-fill-1", when=when
        )
        return [fill, fill.model_copy()]

    def reordered_stream(self, child, *, when: datetime) -> list[OrderEvent | FillEvent]:
        """Fill delivered BEFORE the acceptance that maps broker<->client IDs."""
        early_fill = self.fill_event(child, qty="4", broker_fill_id="reorder-fill-1", when=when)
        accept = self.order_event(child, "ACCEPTED", when=when)
        return [early_fill, accept]

    def delayed_cancel_stream(self, child, *, when: datetime) -> list[OrderEvent | FillEvent]:
        """Cancel acknowledged late, after a partial fill landed first."""
        partial = self.order_event(child, "PARTIALLY_FILLED", filled_qty="4", when=when)
        fill = self.fill_event(child, qty="4", broker_fill_id="delayed-fill-1", when=when)
        canceled = self.order_event(child, "CANCELED", filled_qty="4", when=when)
        return [partial, fill, canceled]
