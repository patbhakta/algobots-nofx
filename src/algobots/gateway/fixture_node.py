"""A fake node that speaks the real node's wire shape.

P1.1's "Done when" is *contract tests pass against a fixture node*. This is
that node: it reads ``algobots:cmd:<node>`` exactly as P1.3's ``CommandActor``
will, and it answers with the Nautilus event JSON captured in P0.3
(artifacts/ALG-3350/p03-redis-xread-evidence.md) — the same field names, the
same ``"2.20 USD"`` money strings, the same ISO-8601 timestamps.

It is a fixture, not a simulator, and the distinction matters: it decides
nothing. Fill prices are supplied by the test, not computed from a book, so
nothing here can quietly become the source of a price the gateway reports.
What it does faithfully is the *shape* and the *sequence* — Initialized ->
Submitted -> Accepted -> Filled, PositionOpened -> PositionClosed — which is
what the gateway's fold is being tested against.

Lives in ``src/`` rather than ``tests/`` because P1.5 (GATE G1) needs the same
fake to drive the end-to-end paper test, and P1.3 needs it to have a consumer
whose behaviour it must match.
"""

from __future__ import annotations

import itertools
import time
from dataclasses import dataclass, field
from decimal import Decimal

from algobots.gateway import node_events as NE
from algobots.gateway.node_events import HEARTBEAT
from algobots.gateway.nodes import InMemoryCommandBus, Node, NodeRegistry
from algobots.gateway.projection import InMemoryProjection, Projection, iso


@dataclass
class FixtureNode:
    """One node, one account, driven explicitly by the test.

    ``drain`` consumes whatever the gateway admitted and emits the node-side
    events for it; nothing happens on a timer, so every test is deterministic.
    """

    node: Node
    registry: NodeRegistry
    projection: Projection
    bus: InMemoryCommandBus
    clock: float = field(default_factory=time.time)
    currency: str = "USD"
    #: Price the next market fill prints at. The test sets it; the node never
    #: invents one, so no fixture price can be mistaken for a quote.
    fill_px: Decimal = Decimal("1.10005")
    commission: Decimal = Decimal("2.20")
    _ids: itertools.count = field(default_factory=lambda: itertools.count(1))
    _position: str | None = None

    # --- node -> gateway ------------------------------------------------------

    def tick(self, seconds: float = 1.0) -> float:
        self.clock += seconds
        return self.clock

    def _emit(self, payload: dict) -> dict | None:
        return NE.ingest(payload, registry=self.registry, projection=self.projection)

    def heartbeat(self, *, reconciled: bool = True) -> dict | None:
        """The node's liveness beat — what makes it fit to take an order."""
        return self._emit(
            {
                "type": HEARTBEAT,
                "node": self.node.node,
                "account_id": self.node.nautilus_account_id,
                "reconciled": reconciled,
                "ts": self.clock,
                "ts_event": iso(self.clock),
            }
        )

    def account_state(self, total: str, *, free: str | None = None, locked: str = "0.00") -> None:
        """A Nautilus ``AccountState``: the only source of a balance."""
        self._emit(
            {
                "type": "AccountState",
                "account_id": self.node.nautilus_account_id,
                "account_type": "CASH",
                "base_currency": self.currency,
                "balances": [
                    {
                        "total": f"{total} {self.currency}",
                        "locked": f"{locked} {self.currency}",
                        "free": f"{free or total} {self.currency}",
                        "currency": self.currency,
                    }
                ],
                "margins": [],
                "reported": True,
                "ts_event": iso(self.clock),
                "ts_init": iso(self.clock),
            }
        )

    # --- gateway -> node ------------------------------------------------------

    def drain(self, *, fill: bool = True, accept: bool = True) -> list[dict]:
        """Consume this node's commands and emit the events they cause.

        ``fill=False`` stops after ``OrderAccepted``, which is how a test gets
        a working order to cancel.
        """
        emitted: list[dict] = []
        for command in self.bus.drain(self.node.node):
            if command.get("command") == "submit_order":
                emitted += self._submit(command, fill=fill, accept=accept)
            elif command.get("command") == "cancel_order":
                emitted += self._cancel(command)
        return [e for e in emitted if e]

    def _submit(self, command: dict, *, fill: bool, accept: bool) -> list[dict | None]:
        client_order_id = command["client_order_id"]
        side = command["side"].upper()
        base = {
            "trader_id": self.node.node.upper(),
            "strategy_id": "GatewayCommandActor-000",
            "instrument_id": command["symbol"],
            "client_order_id": client_order_id,
        }
        out = [
            self._emit(
                {
                    **base,
                    "type": "OrderInitialized",
                    "order_side": side,
                    "order_type": command["order_type"].upper(),
                    "quantity": command["qty"],
                    "price": command.get("limit_px"),
                    "time_in_force": (command.get("time_in_force") or "gtc").upper(),
                    "post_only": False,
                    "reduce_only": bool(command.get("reduce_only")),
                    "options": {},
                    "ts_init": iso(self.tick(0.0)),
                    "ts_event": iso(self.clock),
                    "reconciliation": False,
                }
            ),
            self._emit(
                {
                    **base,
                    "type": "OrderSubmitted",
                    "account_id": self.node.nautilus_account_id,
                    "ts_event": iso(self.tick(0.1)),
                    "ts_init": iso(self.clock),
                }
            ),
        ]
        venue_order_id = f"SIM-1-{next(self._ids):03d}"
        if accept:
            out.append(
                self._emit(
                    {
                        **base,
                        "type": "OrderAccepted",
                        "venue_order_id": venue_order_id,
                        "account_id": self.node.nautilus_account_id,
                        "ts_event": iso(self.tick(0.1)),
                        "ts_init": iso(self.clock),
                    }
                )
            )
        if not fill:
            return out

        qty = command["qty"]
        position_id = self._position or f"{venue_order_id}-P"
        out.append(
            self._emit(
                {
                    **base,
                    "type": "OrderFilled",
                    "venue_order_id": venue_order_id,
                    "account_id": self.node.nautilus_account_id,
                    "trade_id": f"T-{client_order_id}",
                    "position_id": position_id,
                    "order_side": side,
                    "order_type": command["order_type"].upper(),
                    "last_qty": qty,
                    "last_px": str(self.fill_px),
                    "currency": self.currency,
                    "commission": f"{self.commission} {self.currency}",
                    "liquidity_side": "TAKER",
                    "ts_event": iso(self.tick(0.1)),
                    "ts_init": iso(self.clock),
                    "info": {},
                    "reconciliation": False,
                }
            )
        )
        closing = self._position is not None and bool(command.get("reduce_only"))
        position = {
            "trader_id": base["trader_id"],
            "strategy_id": base["strategy_id"],
            "instrument_id": command["symbol"],
            "position_id": position_id,
            "account_id": self.node.nautilus_account_id,
            "opening_order_id": client_order_id,
            "entry": side if not closing else ("BUY" if side == "SELL" else "SELL"),
            "last_qty": qty,
            "last_px": str(self.fill_px),
            "currency": self.currency,
            "avg_px_open": float(self.fill_px),
            "peak_qty": qty,
            "ts_opened": iso(self.clock),
            "ts_init": iso(self.clock),
            "duration_ns": 0,
        }
        if closing:
            self._position = None
            out.append(
                self._emit(
                    {
                        **position,
                        "type": "PositionClosed",
                        "closing_order_id": client_order_id,
                        "side": "FLAT",
                        "signed_qty": 0.0,
                        "quantity": "0",
                        "avg_px_close": float(self.fill_px),
                        "realized_return": 0.0,
                        "realized_pnl": f"-{self.commission * 2} {self.currency}",
                        "ts_closed": iso(self.clock),
                        "ts_event": iso(self.clock),
                    }
                )
            )
        else:
            self._position = position_id
            out.append(
                self._emit(
                    {
                        **position,
                        "type": "PositionOpened",
                        "side": "LONG" if side == "BUY" else "SHORT",
                        "signed_qty": float(Decimal(qty)),
                        "quantity": qty,
                        "realized_pnl": f"-{self.commission} {self.currency}",
                        "ts_event": iso(self.clock),
                    }
                )
            )
        return out

    def _cancel(self, command: dict) -> list[dict | None]:
        return [
            self._emit(
                {
                    "type": "OrderCanceled",
                    "trader_id": self.node.node.upper(),
                    "strategy_id": "GatewayCommandActor-000",
                    "client_order_id": command["client_order_id"],
                    "account_id": self.node.nautilus_account_id,
                    "ts_event": iso(self.tick(0.1)),
                    "ts_init": iso(self.clock),
                }
            )
        ]


def fixture_stack(
    *,
    account_id: str = "laya",
    node_name: str = "nautilus-laya",
    venue: str = "PAPER_LAYA",
    nautilus_account_id: str = "SIM-001",
    display_name: str = "Laya paper",
    projection: Projection | None = None,
) -> tuple[NodeRegistry, Projection, InMemoryCommandBus, FixtureNode]:
    """A registry, projection, bus and one fixture node, wired together.

    ``projection`` defaults to the in-memory one. P1.2 passes a
    :class:`~algobots.gateway.store.SqlProjection` instead, so the same fixture
    node — the same emitted Nautilus payloads — drives the durable store, and a
    difference between the two stores shows up as a failing test rather than as
    a deploy that behaves unlike CI.
    """
    registry = NodeRegistry()
    node = registry.add(
        Node(
            node=node_name,
            account_id=account_id,
            display_name=display_name,
            venue=venue,
            nautilus_account_id=nautilus_account_id,
        )
    )
    store = InMemoryProjection() if projection is None else projection
    bus = InMemoryCommandBus()
    return registry, store, bus, FixtureNode(node, registry, store, bus)


__all__ = ["FixtureNode", "fixture_stack"]
