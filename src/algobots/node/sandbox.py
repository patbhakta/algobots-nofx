"""A node that executes commands and publishes events, with no engine.

GATE G1 has to run in CI on every merge (ALG-3373), and CI installs the ``dev``
extra — ``nautilus_trader`` lives in ``workers`` and is not there. A gate that
only ran where the engine happened to be installed would not be a gate, so this
module is the node the gate drives: the real
:class:`~algobots.node.command_stream.CommandStream`, the real
:class:`~algobots.node.command_actor.CommandActor`, the real Redis streams in
both directions, and an :class:`~algobots.node.command_actor.ExecutionSurface`
that emits the P0.3 event shapes instead of calling a venue.

What that leaves un-exercised is one file,
:mod:`algobots.node.nautilus_actor` — the translation from a ``SubmitOrder``
into an engine order. Everything else on the path a fill takes is the
production code path, including both Redis legs and the Postgres fold.
``scripts/phase0_redis_egress.py`` is where the engine's own egress is proven
against a real node, which is why this fixture may publish in that envelope
without inventing it.

**This node holds no reference to the gateway's projection.** It gets its own
throwaway one, which nothing reads. That is not tidiness: if the sandbox could
write to the store the gateway serves, the gate would pass whenever the
fixture worked and would say nothing at all about whether the two Redis legs
and the fold between them do.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from algobots.gateway.fixture_node import FixtureNode
from algobots.gateway.nodes import Node, NodeRegistry
from algobots.gateway.projection import InMemoryProjection
from algobots.node.command_actor import CommandActor
from algobots.node.command_stream import CommandStream
from algobots.node.commands import SubmitOrder
from algobots.node.event_egress import EventEgress

#: Nautilus ``OrderStatus`` names, as the actor's dedupe reads them.
SUBMITTED = "SUBMITTED"
ACCEPTED = "ACCEPTED"
FILLED = "FILLED"
PENDING_CANCEL = "PENDING_CANCEL"
CANCELED = "CANCELED"
DENIED = "DENIED"


def trader_id_for(node: str) -> str:
    """``nautilus-laya`` -> ``NAUTILUS-LAYA``.

    The same derivation ``FixtureNode`` stamps into ``trader_id``, so the
    stream keys this node writes carry the trader id its payloads name.
    """
    return node.upper()


@dataclass
class SandboxExecution:
    """An ``ExecutionSurface`` whose venue is the P0.3 event sequence.

    It prices nothing and matches nothing — ``fill_px`` is the fixture's, set
    by whoever builds the node — but it does model the one venue rule P1.3's
    guarantee rests on: an order may not exist twice under one client order id.
    """

    fixture: FixtureNode
    #: ``False`` stops at ``OrderAccepted``: a working order to cancel.
    fill: bool = True
    #: Client order id -> Nautilus ``OrderStatus``. In a real node this is the
    #: engine's reconciled cache, which is why ``CommandActor`` asks for it by
    #: name rather than keeping a set of its own.
    statuses: dict[str, str] = field(default_factory=dict)

    def status(self, client_order_id: str) -> str | None:
        return self.statuses.get(client_order_id)

    def submit(self, order: SubmitOrder) -> None:
        if order.client_order_id in self.statuses:
            # What Nautilus does with a repeated id: denies it, as an event, and
            # keeps running. Raising would leave the stream entry unacked and
            # take the node down on a duplicate the actor is built to absorb —
            # and the denial is more useful, because it reaches the projection.
            self.fixture.deny(order.client_order_id, reason="duplicate client order id")
            self.statuses[order.client_order_id] = DENIED
            return

        # Recorded before the events are emitted, so a concurrent redelivery
        # sees the id as known rather than submitting a second order while the
        # first one's events are still being published.
        self.statuses[order.client_order_id] = SUBMITTED
        self.fixture.execute(_command(order), fill=self.fill)
        self.statuses[order.client_order_id] = FILLED if self.fill else ACCEPTED

    def cancel(self, client_order_id: str) -> None:
        self.statuses[client_order_id] = PENDING_CANCEL
        self.fixture.execute(
            {"command": "cancel_order", "client_order_id": client_order_id},
        )
        self.statuses[client_order_id] = CANCELED


def _command(order: SubmitOrder) -> dict[str, Any]:
    """A parsed ``SubmitOrder`` back into the command dict the fixture reads.

    The round trip is deliberate rather than wasteful: it means the fixture is
    driven by what ``commands.parse`` *accepted*, so a field the parser drops
    cannot reach the venue through this path either.
    """
    return {
        "command": "submit_order",
        "client_order_id": order.client_order_id,
        "account_id": order.account_id,
        "symbol": order.symbol,
        "side": order.side,
        "qty": str(order.qty),
        "order_type": order.order_type,
        "limit_px": None if order.limit_px is None else str(order.limit_px),
        "time_in_force": order.time_in_force,
        "reduce_only": order.reduce_only,
    }


@dataclass
class SandboxNode:
    """The assembled node: a command stream in, an event stream out."""

    stream: CommandStream
    execution: SandboxExecution
    egress: EventEgress
    node: Node

    def heartbeat(self, *, reconciled: bool = True, ts: float | None = None) -> str:
        """Publish the beat that makes this node fit to take an order."""
        return self.egress.heartbeat(
            node=self.node.node,
            nautilus_account_id=self.node.nautilus_account_id,
            ts=time.time() if ts is None else ts,
            reconciled=reconciled,
        )

    def account_state(self, total: str, *, free: str | None = None) -> None:
        """Publish an ``AccountState`` — the only source of a balance."""
        self.execution.fixture.account_state(total, free=free)

    def run(self, *, until: Any = None) -> None:
        self.stream.run(until=until)


def sandbox_node(
    *,
    client: Any,
    account_id: str = "laya",
    node_name: str = "nautilus-laya",
    venue: str = "PAPER_LAYA",
    nautilus_account_id: str = "SIM-001",
    display_name: str = "Laya paper",
    fill_px: Decimal = Decimal("1.10005"),
    fill: bool = True,
    consumer: str = "node-1",
    block_ms: int | None = None,
    log: Any = None,
) -> SandboxNode:
    """Wire a sandbox node onto ``client``'s command and event streams.

    ``client`` is a real ``redis.Redis`` in the gate and a fake in the unit
    tests; nothing here knows which.
    """
    own_registry = NodeRegistry()
    node = own_registry.add(
        Node(
            node=node_name,
            account_id=account_id,
            display_name=display_name,
            venue=venue,
            nautilus_account_id=nautilus_account_id,
        )
    )
    egress = EventEgress(client=client, trader_id=trader_id_for(node_name))
    fixture = FixtureNode(
        node=node,
        registry=own_registry,
        # Never read: the gateway's fold is the only one that counts, and this
        # node is not allowed to reach it (see the module docstring).
        projection=InMemoryProjection(),
        bus=None,  # type: ignore[arg-type] — commands arrive via CommandStream
        fill_px=fill_px,
        sink=egress.publish,
    )
    execution = SandboxExecution(fixture=fixture, fill=fill)
    actor = CommandActor(execution=execution, node=node_name, log=log)
    stream = CommandStream(
        client=client,
        actor=actor,
        node=node_name,
        consumer=consumer,
        log=log,
        **({} if block_ms is None else {"block_ms": block_ms}),
    )
    return SandboxNode(stream=stream, execution=execution, egress=egress, node=node)


__all__ = [
    "ACCEPTED",
    "CANCELED",
    "DENIED",
    "FILLED",
    "PENDING_CANCEL",
    "SUBMITTED",
    "SandboxExecution",
    "SandboxNode",
    "sandbox_node",
    "trader_id_for",
]
