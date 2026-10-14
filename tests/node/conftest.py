"""A venue that enforces Nautilus' duplicate-client-order-id law, and a stream.

``SandboxVenue`` is not a simulator — it decides no price and matches nothing.
It models exactly one rule, the one P1.3's guarantee rests on:

    an order may not be submitted twice with the same ``ClientOrderId``.

Nautilus enforces that in the engine (a second order with a known id is denied
before it reaches a venue), so a double that *allowed* it would let a broken
``CommandActor`` pass. This one raises, which means the done-when test fails
loudly on a duplicate instead of quietly counting two orders.

The same objects back the ``CommandStream`` tests through ``FakeRedis``, which
implements the four stream calls the reader uses with real consumer-group
semantics — pending list included, because redelivery is the thing being
tested and a fake that acked eagerly would test nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from algobots.node.commands import SubmitOrder


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


@dataclass
class FakeRedis:
    """The four stream commands ``CommandStream`` uses, with pending lists.

    Entry ids are ``"<n>-0"`` so they sort and read like real ones. Only one
    consumer group is modelled, which is all a node ever has.
    """

    streams: dict[str, list[tuple[str, dict[str, str]]]] = field(default_factory=dict)
    groups: dict[tuple[str, str], int] = field(default_factory=dict)
    #: (stream, group) -> entry ids delivered but not yet acked.
    pending: dict[tuple[str, str], list[str]] = field(default_factory=dict)
    _seq: int = 0

    def xadd(self, key: str, fields: dict[str, str]) -> str:
        self._seq += 1
        entry_id = f"{self._seq}-0"
        self.streams.setdefault(key, []).append((entry_id, dict(fields)))
        return entry_id

    def xgroup_create(self, key: str, group: str, id: str = "0", mkstream: bool = False) -> None:  # noqa: A002 — redis' own kwarg name
        if (key, group) in self.groups:
            raise RuntimeError("BUSYGROUP Consumer Group name already exists")
        if mkstream:
            self.streams.setdefault(key, [])
        self.groups[(key, group)] = 0
        self.pending[(key, group)] = []

    def xreadgroup(
        self,
        group: str,
        consumer: str,
        streams: dict[str, str],
        count: int = 10,
        block: int | None = None,
    ) -> list[Any]:
        out = []
        for key, cursor in streams.items():
            entries = self.streams.get(key, [])
            if cursor == ">":
                start = self.groups.get((key, group), 0)
                batch = entries[start : start + count]
                self.groups[(key, group)] = start + len(batch)
                self.pending.setdefault((key, group), []).extend(eid for eid, _ in batch)
            else:
                # The pending list: everything delivered and not acked.
                owed = set(self.pending.get((key, group), []))
                batch = [(eid, f) for eid, f in entries if eid in owed][:count]
            if batch:
                out.append((key, batch))
        return out

    def xack(self, key: str, group: str, entry_id: str) -> int:
        owed = self.pending.setdefault((key, group), [])
        if entry_id in owed:
            owed.remove(entry_id)
            return 1
        return 0

    def pending_count(self, key: str, group: str) -> int:
        return len(self.pending.get((key, group), []))


@pytest.fixture
def venue() -> SandboxVenue:
    return SandboxVenue()


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()
