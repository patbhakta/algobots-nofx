"""Which node serves which account, and the command stream it reads.

One account, one node, one Nautilus ``TradingNode`` — the worker-isolation rule
from ALG-3259 restated at the gateway: there is no shared execution process and
no fallback path when a node is unfit. ``require_fit`` is the bridge's
``orderapi.worker_available`` discipline (reconciled + heartbeat-fresh) with the
truth moved from a heartbeat file to the node's own event stream, which is
where Phase 1 reads everything else from too.

Admitted commands go to ``algobots:cmd:<node>`` as JSON. P1.3's ``CommandActor``
is the consumer; its idempotency key is the Nautilus client order id, so this
module never invents an id of its own.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, Protocol

from algobots.gateway.errors import (
    LIVE_DISABLED,
    NODE_UNKNOWN,
    WORKER_UNAVAILABLE,
    GatewayError,
)

#: A node silent for longer than this is unfit to take an order. Matches the
#: workers' ``supervisor.HEARTBEAT_STALE_S`` so the two layers agree.
HEARTBEAT_STALE_S = 45.0

#: The Nautilus build Phase 1 is pinned to (roadmap rule 5). ``/health``
#: reports it and the contract declares it as a `const`, so a drift between
#: the two is a failing test rather than a surprise in production.
NAUTILUS_PIN = "2.0.0rc9"

PAPER = "PAPER"


@dataclass
class Node:
    """One Nautilus node and the single account it trades.

    ``nautilus_account_id`` is the id the node's own events carry (e.g.
    ``SIM-001``); ``account_id`` is the id NoFX knows. Keeping both is what
    lets ``node_events`` fold a raw Nautilus payload onto the right account
    without the node needing to know AlgoBots' naming.
    """

    node: str
    account_id: str
    display_name: str
    venue: str
    nautilus_account_id: str
    mode: str = PAPER
    reconciled: bool = False
    last_heartbeat: float | None = None
    #: Why a deployment node may not take new orders (stopped, paused, breaker).
    #: The node stays registered so its in-flight fills still fold.
    halted: str = ""

    def fit(self, now: float) -> tuple[bool, str]:
        """Is this node fit to take an order? (why-not text otherwise)."""
        if self.halted:
            return False, self.halted
        if self.last_heartbeat is None:
            return False, "no node heartbeat"
        if not self.reconciled:
            return False, "node is still reconciling — entry-frozen"
        if now - self.last_heartbeat > HEARTBEAT_STALE_S:
            return False, "node heartbeat stale"
        return True, ""


class CommandBus(Protocol):
    """``algobots:cmd:<node>``: admitted commands out, nothing in."""

    def publish(self, node: str, command: dict[str, Any]) -> str:
        """Append one command for ``node``; returns its stream id."""


@dataclass
class InMemoryCommandBus:
    """The command stream without Redis — the fixture node reads from this.

    Same contract as :class:`RedisCommandBus`: append-only, ids monotonic,
    nothing is ever removed by the publisher.
    """

    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    def publish(self, node: str, command: dict[str, Any]) -> str:
        self.published.append((node, dict(command)))
        return str(len(self.published))

    def drain(self, node: str) -> Iterator[dict[str, Any]]:
        """Consume this node's pending commands (the node's side of the bus)."""
        keep: list[tuple[str, dict[str, Any]]] = []
        taken: list[dict[str, Any]] = []
        for target, command in self.published:
            (taken if target == node else keep).append(command)
        self.published = keep
        return iter(taken)

    def commands_for(self, node: str) -> list[dict[str, Any]]:
        return [c for target, c in self.published if target == node]


@dataclass
class RedisCommandBus:
    """``XADD algobots:cmd:<node>`` with the command as a single JSON field.

    A stream, not a list: P1.3 needs consumer-group semantics and an id it can
    acknowledge, and the node restarting may not silently drop commands.
    """

    client: Any  # redis.Redis — not imported here; the API process has no redis dep

    def publish(self, node: str, command: dict[str, Any]) -> str:
        return str(
            self.client.xadd(f"algobots:cmd:{node}", {"command": json.dumps(command, default=str)})
        )


@dataclass
class NodeRegistry:
    """The gateway's view of the fleet: accounts, their nodes, their fitness."""

    nodes: dict[str, Node] = field(default_factory=dict)

    def add(self, node: Node) -> Node:
        # Copy-on-write: deployment sync adds nodes while routes iterate them.
        self.nodes = {**self.nodes, node.node: node}
        return node

    def by_account(self, account_id: str) -> Node | None:
        return next((n for n in self.nodes.values() if n.account_id == account_id), None)

    def by_nautilus_account(self, nautilus_account_id: str) -> Node | None:
        return next(
            (n for n in self.nodes.values() if n.nautilus_account_id == nautilus_account_id), None
        )

    def accounts(self) -> list[Node]:
        """Every known account, insertion-ordered (the contract says oldest first)."""
        return list(self.nodes.values())

    def heartbeat(self, node: str, *, reconciled: bool = True, now: float | None = None) -> None:
        entry = self.nodes.get(node)
        if entry is None:
            raise GatewayError(404, NODE_UNKNOWN, f"node {node!r} is not registered")
        entry.reconciled = reconciled
        entry.last_heartbeat = time.time() if now is None else now

    def require_fit(self, account_id: str, *, now: float | None = None) -> Node:
        """The account's node, or the typed refusal. There is no fallback.

        ``PAPER``-only is checked here too: an account whose node is configured
        for anything else is refused with ``live_disabled`` before fitness is
        considered, so a misconfiguration cannot be masked by a healthy node.
        """
        now = time.time() if now is None else now
        node = self.by_account(account_id)
        if node is None:
            raise GatewayError(
                503, WORKER_UNAVAILABLE, f"account {account_id}: no node is registered for it"
            )
        if node.mode != PAPER:
            raise GatewayError(
                403,
                LIVE_DISABLED,
                f"account {account_id}: mode {node.mode} — no live venue approved",
            )
        ok, why = node.fit(now)
        if not ok:
            raise GatewayError(
                503, WORKER_UNAVAILABLE, f"node {node.node}: {why} — no fallback exists"
            )
        return node


__all__ = [
    "HEARTBEAT_STALE_S",
    "NAUTILUS_PIN",
    "PAPER",
    "CommandBus",
    "InMemoryCommandBus",
    "Node",
    "NodeRegistry",
    "RedisCommandBus",
]
