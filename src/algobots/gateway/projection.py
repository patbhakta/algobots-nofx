"""What the nodes have told us, in the shapes the contract returns.

Everything the gateway reports — orders, fills, positions, balances — is a fold
of the node event stream. Nothing here is computed from a price the gateway
guessed: if no node has said it, the gateway does not know it.

P1.2 replaces :class:`InMemoryProjection` with the Postgres projection, and the
requirement it inherits is already visible in this file's shape: the rows are
derived from an append-only event log, so rebuilding them from ``seq`` 0 after
a gateway restart yields the same state. The ``Projection`` protocol is the
contract between the two sprints.

Money and quantities are kept as :class:`~decimal.Decimal` and rendered with
``dec_str``: plain digits, never exponent notation, because the contract's
``Decimal`` schema is ``^-?[0-9]+(\\.[0-9]+)?$`` and a float would round-trip
through binary floating point on the way to a member's balance.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

ZERO = Decimal(0)

#: Lifecycle states a node can no longer move an order out of.
TERMINAL = frozenset({"filled", "cancelled", "rejected", "expired"})


def dec_str(value: Decimal | int | str) -> str:
    """Render a decimal the way the contract's ``Decimal`` schema requires."""
    d = value if isinstance(value, Decimal) else Decimal(str(value))
    text = format(d.normalize() if d == d.to_integral_value() else d, "f")
    return "0" if text in ("-0", "") else text


def iso(ts: float | str | datetime) -> str:
    """UTC, milliseconds, trailing ``Z`` — the node's own ``ts_event`` format."""
    if isinstance(ts, str):
        moment = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    elif isinstance(ts, datetime):
        moment = ts
    else:
        moment = datetime.fromtimestamp(ts, UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


@dataclass(frozen=True)
class FillRow:
    trade_id: str
    qty: Decimal
    px: Decimal
    ts_event: str
    commission: Decimal | None = None
    commission_currency: str | None = None

    def contract(self) -> dict[str, Any]:
        body = {
            "trade_id": self.trade_id,
            "qty": dec_str(self.qty),
            "px": dec_str(self.px),
            "ts_event": self.ts_event,
        }
        if self.commission is not None:
            body["commission"] = dec_str(self.commission)
        if self.commission_currency:
            body["commission_currency"] = self.commission_currency
        return body


@dataclass(frozen=True)
class OrderRow:
    """One order, as the contract's ``Order`` plus what only we need.

    ``fingerprint`` and ``node`` are gateway bookkeeping — the idempotency
    comparison and the command target — and are never serialized: the contract
    sets ``additionalProperties: false``, so leaking one is a hard failure.
    """

    client_order_id: str
    account_id: str
    symbol: str
    side: str
    qty: Decimal
    order_type: str
    status: str
    submitted_at: str
    updated_at: str
    mode: str = "PAPER"
    venue_order_id: str | None = None
    filled_qty: Decimal = ZERO
    avg_px: Decimal | None = None
    limit_px: Decimal | None = None
    time_in_force: str | None = None
    reason: str | None = None
    fills: tuple[FillRow, ...] = ()
    fingerprint: str = ""
    node: str = ""

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL

    def contract(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "client_order_id": self.client_order_id,
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": dec_str(self.qty),
            "filled_qty": dec_str(self.filled_qty),
            "order_type": self.order_type,
            "status": self.status,
            "mode": self.mode,
            "venue_order_id": self.venue_order_id,
            "reason": self.reason,
            "fills": [f.contract() for f in self.fills],
            "submitted_at": self.submitted_at,
            "updated_at": self.updated_at,
        }
        if self.avg_px is not None:
            body["avg_px"] = dec_str(self.avg_px)
        if self.limit_px is not None:
            body["limit_px"] = dec_str(self.limit_px)
        if self.time_in_force:
            body["time_in_force"] = self.time_in_force
        return body


@dataclass(frozen=True)
class PositionRow:
    account_id: str
    symbol: str
    side: str
    qty: Decimal
    avg_px: Decimal
    opened_at: str
    position_id: str = ""
    unrealized_pnl: Decimal | None = None
    realized_pnl: Decimal | None = None

    def contract(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "account_id": self.account_id,
            "symbol": self.symbol,
            "side": self.side,
            "qty": dec_str(self.qty),
            "avg_px": dec_str(self.avg_px),
            "opened_at": self.opened_at,
        }
        if self.unrealized_pnl is not None:
            body["unrealized_pnl"] = dec_str(self.unrealized_pnl)
        if self.realized_pnl is not None:
            body["realized_pnl"] = dec_str(self.realized_pnl)
        return body


class Projection(Protocol):
    """What P1.2's Postgres projection has to be able to do."""

    def order(self, client_order_id: str) -> OrderRow | None: ...

    def orders(
        self, *, accounts: tuple[str, ...], status: str | None = None, limit: int = 100
    ) -> list[OrderRow]: ...

    def put_order(self, order: OrderRow) -> OrderRow: ...

    def positions(self, *, accounts: tuple[str, ...]) -> list[PositionRow]: ...

    def balances(self, account_id: str) -> list[dict[str, Any]]: ...

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]: ...

    def events_since(self, seq: int, *, accounts: tuple[str, ...]) -> list[dict[str, Any]]: ...

    @property
    def as_of(self) -> str: ...


@dataclass
class InMemoryProjection:
    """The projection with the event log held in this process.

    Enough to serve the whole contract against a fixture node, which is P1.1's
    "Done when". It is deliberately not durable: P1.2's job is to make the same
    reads come back after a restart, and a convincing in-memory substitute for
    that would only hide the work.
    """

    _orders: dict[str, OrderRow] = field(default_factory=dict)
    _order_seq: list[str] = field(default_factory=list)  # insertion order, oldest first
    _positions: dict[str, PositionRow] = field(default_factory=dict)  # by position_id
    _balances: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    _events: list[dict[str, Any]] = field(default_factory=list)
    _as_of: str = field(default_factory=lambda: iso(datetime.now(UTC)))

    # --- reads ---------------------------------------------------------------

    def order(self, client_order_id: str) -> OrderRow | None:
        return self._orders.get(client_order_id)

    def orders(
        self, *, accounts: tuple[str, ...], status: str | None = None, limit: int = 100
    ) -> list[OrderRow]:
        rows = [self._orders[k] for k in reversed(self._order_seq)]  # newest first
        rows = [r for r in rows if r.account_id in accounts]
        if status is not None:
            rows = [r for r in rows if r.status == status]
        return rows[:limit]

    def positions(self, *, accounts: tuple[str, ...]) -> list[PositionRow]:
        return [p for p in self._positions.values() if p.account_id in accounts]

    def balances(self, account_id: str) -> list[dict[str, Any]]:
        return list(self._balances.get(account_id, ()))

    def events_since(self, seq: int, *, accounts: tuple[str, ...]) -> list[dict[str, Any]]:
        return [e for e in self._events if e["seq"] > seq and e["account_id"] in accounts]

    @property
    def as_of(self) -> str:
        return self._as_of

    @property
    def head(self) -> int:
        """The newest ``seq``; a client resuming from here loses nothing."""
        return self._events[-1]["seq"] if self._events else 0

    # --- folds (node_events is the only caller) ------------------------------

    def put_order(self, order: OrderRow) -> OrderRow:
        if order.client_order_id not in self._orders:
            self._order_seq.append(order.client_order_id)
        self._orders[order.client_order_id] = order
        return order

    def amend_order(self, client_order_id: str, **changes: Any) -> OrderRow | None:
        """Apply a node-reported change. Unknown orders are ignored, not created:
        an order the gateway never admitted has no admission record, and
        inventing one would make a refused intent look admitted."""
        current = self._orders.get(client_order_id)
        if current is None:
            return None
        return self.put_order(replace(current, **changes))

    def position(self, position_id: str) -> PositionRow | None:
        return self._positions.get(position_id)

    def put_position(self, position: PositionRow) -> PositionRow:
        self._positions[position.position_id or position.symbol] = position
        return position

    def drop_position(self, position_id: str) -> None:
        self._positions.pop(position_id, None)

    def put_balances(self, account_id: str, balances: list[dict[str, Any]]) -> None:
        self._balances[account_id] = balances

    def append_event(self, event: dict[str, Any]) -> dict[str, Any]:
        """Assign the next ``seq`` and record it. Monotonic per gateway: it is
        both the resume cursor and the dedupe key for at-least-once delivery."""
        stamped = {"seq": len(self._events) + 1, **event}
        self._events.append(stamped)
        self._as_of = max(self._as_of, str(stamped.get("ts_event") or self._as_of))
        return stamped


__all__ = [
    "TERMINAL",
    "ZERO",
    "FillRow",
    "InMemoryProjection",
    "OrderRow",
    "PositionRow",
    "Projection",
    "dec_str",
    "iso",
]
