"""A venue that enforces Nautilus' duplicate-client-order-id law, and a stream.

``SandboxVenue`` is not a simulator — it decides no price and matches nothing.
It models exactly one rule, the one P1.3's guarantee rests on:

    an order may not be submitted twice with the same ``ClientOrderId``.

Nautilus enforces that in the engine (a second order with a known id is denied
before it reaches a venue), so a double that *allowed* it would let a broken
``CommandActor`` pass. This one raises, which means the done-when test fails
loudly on a duplicate instead of quietly counting two orders.

The same objects back the ``CommandStream`` tests through ``FakeRedis``, which
since P1.5 lives in ``tests/fakes``: the gateway's event-ingest tests need the
same stream semantics from the other side of the transport, and two fakes that
could disagree about redelivery would be worse than one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from algobots.node.commands import SubmitOrder
from tests.fakes import FakeRedis


class DuplicateClientOrderId(AssertionError):
    """What Nautilus does with a repeated id, as an immediate test failure."""


@dataclass
class SandboxVenue:
    """Orders the venue knows, by client order id, with their status."""

    orders: dict[str, SubmitOrder] = field(default_factory=dict)
    statuses: dict[str, str] = field(default_factory=dict)
    #: Every ``submit``/``cancel`` call, in order — the audit the tests read.
    calls: list[tuple[str, str]] = field(default_factory=list)

    # --- the ExecutionSurface protocol ---------------------------------------

    def status(self, client_order_id: str) -> str | None:
        return self.statuses.get(client_order_id)

    def submit(self, order: SubmitOrder) -> None:
        if order.client_order_id in self.orders:
            raise DuplicateClientOrderId(
                f"{order.client_order_id} submitted twice — Nautilus would deny this"
            )
        self.orders[order.client_order_id] = order
        self.statuses[order.client_order_id] = "ACCEPTED"
        self.calls.append(("submit", order.client_order_id))

    def cancel(self, client_order_id: str) -> None:
        self.statuses[client_order_id] = "PENDING_CANCEL"
        self.calls.append(("cancel", client_order_id))

    # --- what the node's event stream would later report ---------------------

    def confirm_cancel(self, client_order_id: str) -> None:
        self.statuses[client_order_id] = "CANCELED"

    def fill(self, client_order_id: str) -> None:
        self.statuses[client_order_id] = "FILLED"

    @property
    def order_count(self) -> int:
        """How many orders exist at the venue. The done-when asserts on this."""
        return len(self.orders)

    def submits_of(self, client_order_id: str) -> int:
        return sum(1 for kind, coid in self.calls if kind == "submit" and coid == client_order_id)

    def cancels_of(self, client_order_id: str) -> int:
        return sum(1 for kind, coid in self.calls if kind == "cancel" and coid == client_order_id)


@pytest.fixture
def venue() -> SandboxVenue:
    return SandboxVenue()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()
