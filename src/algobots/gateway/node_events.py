"""Nautilus event JSON, folded into the projection. The only wire-shape module.

These are the exact payloads P0.3 captured off ``algobots:events.*`` on
``.243`` (artifacts/ALG-3350/p03-redis-xread-evidence.md): JSON, with
``timestamps_as_iso8601``, one Nautilus event per stream entry. Quote ticks are
filtered at the node by ``types_filter=[QuoteTick]`` and so never arrive here;
anything that is not an order, position, account or heartbeat event is ignored
rather than guessed at, because an unrecognised event must not become state.

Two rules this module exists to keep:

1. **The node is the only source of truth.** A fill, a venue order id, a
   position — none of them are computed here, only transcribed.
2. **An event for an order the gateway never admitted is dropped.** The
   client order id is the idempotency key the gateway issued at admission
   (P1.3), so an unknown one means a command this gateway did not write.
   Materialising it would make a refused intent indistinguishable from an
   admitted one.

Nautilus 2.0.0rc6 writes the same events in a different envelope from the
1.231 capture (ALG-3405, ``artifacts/ALG-3405/rc6-wire-shapes.md``):
order and position events arrive wrapped in their enum variant
(``{"Filled": {...}}``, ``{"PositionOpened": {...}}``), ``AccountState`` and
position events carry no ``type`` field (it is only on the stream entry), and
every ``ts_*`` is integer nanoseconds even with ``timestamps_as_iso8601``.
:func:`normalize` turns either generation into the flat shape below, so the
fold itself has one input format.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from algobots.gateway.nodes import NodeRegistry
from algobots.gateway.projection import (
    FillRow,
    OrderRow,
    PositionRow,
    Projection,
    dec_str,
    iso,
)

#: Nautilus ``OrderStatus``-ish event names mapped onto the contract's
#: ``OrderStatus`` enum — the node's lifecycle flattened to what NoFX renders.
ORDER_STATUS = {
    "OrderInitialized": "admitted",
    "OrderSubmitted": "submitted",
    "OrderAccepted": "accepted",
    "OrderFilled": "filled",  # narrowed to partially_filled when qty remains
    "OrderCanceled": "cancelled",
    "OrderCancelled": "cancelled",  # tolerate either spelling on the wire
    "OrderExpired": "expired",
    "OrderRejected": "rejected",
    "OrderDenied": "rejected",
}

SIDES = {"BUY": "buy", "SELL": "sell"}
POSITION_SIDES = {"LONG": "buy", "SHORT": "sell"}

#: The node's liveness beat. Nautilus has no cross-engine heartbeat event, so
#: the node emits this one on the same stream; the gateway's fitness check and
#: ``/health`` both read it, and it reaches NoFX as a ``heartbeat`` event.
HEARTBEAT = "AlgoBotsHeartbeat"


def _money(raw: Any) -> tuple[Decimal | None, str | None]:
    """``"2.20 USD"`` -> ``(Decimal("2.20"), "USD")``; bare numbers keep no currency."""
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text:
        return None, None
    amount, _, currency = text.partition(" ")
    try:
        return Decimal(amount), (currency or None)
    except ArithmeticError:
        return None, None


def _dec(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    try:
        return Decimal(str(raw))
    except ArithmeticError:
        return None


#: Integer timestamps above this are nanoseconds (rc6), not epoch seconds.
_NS_FLOOR = 10**17


def normalize(payload: dict[str, Any], entry_type: str = "") -> dict[str, Any]:
    """Either engine generation's event as one flat dict with a ``type``.

    ``entry_type`` is the stream entry's own ``type`` field, which rc6 fills
    (``AccountState``, ``OrderEventAny``) and our heartbeat leaves empty. A
    1.231 payload already has ``type`` and passes through unchanged apart from
    the timestamp rule, which is a no-op for ISO strings and epoch seconds.
    """
    flat = payload
    variant = ""
    if len(payload) == 1:
        ((name, inner),) = payload.items()
        if isinstance(inner, dict) and name[:1].isupper():
            flat, variant = dict(inner), name
    if not flat.get("type"):
        # Position variants are the event name; order variants carry their own
        # ``type`` inside. Anything else takes the stream entry's type.
        kind = variant if variant.startswith("Position") else entry_type
        if kind:
            flat = {**flat, "type": kind}
    stamps = {
        key: value / 1e9
        for key, value in flat.items()
        if key.startswith("ts_") and isinstance(value, int) and value > _NS_FLOOR
    }
    return {**flat, **stamps} if stamps else flat


def ingest(
    payload: dict[str, Any],
    *,
    registry: NodeRegistry,
    projection: Projection,
) -> dict[str, Any] | None:
    """Fold one node event into the projection; return the ``Event`` appended.

    ``None`` means the event carried nothing the contract exposes (a system or
    data event, or an order this gateway never admitted).
    """
    kind = str(payload.get("type") or "")
    if kind == HEARTBEAT:
        return _heartbeat(payload, registry=registry, projection=projection)
    if kind == "AccountState":
        return _account_state(payload, registry=registry, projection=projection)
    if kind.startswith("Position"):
        return _position(payload, registry=registry, projection=projection)
    if kind in ORDER_STATUS:
        return _order(payload, registry=registry, projection=projection)
    return None


def _heartbeat(
    payload: dict[str, Any], *, registry: NodeRegistry, projection: Projection
) -> dict[str, Any] | None:
    node = registry.nodes.get(str(payload.get("node") or ""))
    if node is None:
        return None
    node.reconciled = bool(payload.get("reconciled"))
    node.last_heartbeat = float(payload["ts"]) if payload.get("ts") is not None else None
    ts = iso(payload.get("ts_event") or node.last_heartbeat or 0.0)
    return projection.append_event(
        {"type": "heartbeat", "account_id": node.account_id, "ts_event": ts}
    )


def _account_state(
    payload: dict[str, Any], *, registry: NodeRegistry, projection: Projection
) -> dict[str, Any] | None:
    node = registry.by_nautilus_account(str(payload.get("account_id") or ""))
    if node is None:
        return None
    balances = []
    for raw in payload.get("balances") or []:
        total, currency = _money(raw.get("total"))
        free, _ = _money(raw.get("free"))
        locked, _ = _money(raw.get("locked"))
        currency = raw.get("currency") or currency
        if total is None or free is None or not currency:
            continue
        balance = {"currency": str(currency), "total": dec_str(total), "free": dec_str(free)}
        if locked is not None:
            balance["locked"] = dec_str(locked)
        balances.append(balance)
    projection.put_balances(node.account_id, balances)
    ts = iso(payload.get("ts_event") or 0.0)
    return projection.append_event(
        {
            "type": "balance",
            "account_id": node.account_id,
            "ts_event": ts,
            "account": account_contract(node, balances),
        }
    )


def account_contract(node: Any, balances: list[dict[str, Any]]) -> dict[str, Any]:
    """The contract's ``Account`` for one node. Shared with ``/accounts``."""
    return {
        "account_id": node.account_id,
        "display_name": node.display_name,
        "mode": node.mode,
        "venue": node.venue,
        "node": node.node,
        "balances": balances,
    }


def _position(
    payload: dict[str, Any], *, registry: NodeRegistry, projection: Projection
) -> dict[str, Any] | None:
    node = registry.by_nautilus_account(str(payload.get("account_id") or ""))
    if node is None:
        return None
    position_id = str(payload.get("position_id") or "")
    ts = iso(payload.get("ts_event") or payload.get("ts_closed") or payload.get("ts_init") or 0.0)
    realized, _ = _money(payload.get("realized_pnl"))
    unrealized, _ = _money(payload.get("unrealized_pnl"))

    if payload.get("type") == "PositionClosed":
        projection.drop_position(position_id)
        position = PositionRow(
            account_id=node.account_id,
            symbol=str(payload.get("instrument_id") or ""),
            side=POSITION_SIDES.get(str(payload.get("entry") or ""), "buy"),
            qty=_dec(payload.get("quantity")) or Decimal(0),
            avg_px=_dec(payload.get("avg_px_open")) or Decimal(0),
            opened_at=iso(payload.get("ts_opened") or ts),
            position_id=position_id,
            realized_pnl=realized,
        )
    else:
        existing = projection.position(position_id)
        position = PositionRow(
            account_id=node.account_id,
            symbol=str(payload.get("instrument_id") or ""),
            side=POSITION_SIDES.get(str(payload.get("side") or ""), "buy"),
            qty=_dec(payload.get("quantity")) or Decimal(0),
            avg_px=_dec(payload.get("avg_px_open")) or Decimal(0),
            opened_at=existing.opened_at if existing else iso(payload.get("ts_opened") or ts),
            position_id=position_id,
            realized_pnl=realized,
            unrealized_pnl=unrealized,
        )
        projection.put_position(position)

    return projection.append_event(
        {
            "type": "position",
            "account_id": node.account_id,
            "ts_event": ts,
            "position": position.contract(),
        }
    )


def _order(
    payload: dict[str, Any], *, registry: NodeRegistry, projection: Projection
) -> dict[str, Any] | None:
    client_order_id = str(payload.get("client_order_id") or "")
    if projection.order(client_order_id) is None:
        return None  # rule 2: never materialise an order the gateway did not admit
    ts = iso(payload.get("ts_event") or payload.get("ts_init") or 0.0)
    kind = str(payload["type"])
    venue_order_id = str(payload["venue_order_id"]) if payload.get("venue_order_id") else None
    reason = str(payload["reason"]) if payload.get("reason") else None

    fill: FillRow | None = None
    if kind == "OrderFilled":
        commission, commission_ccy = _money(payload.get("commission"))
        fill = FillRow(
            trade_id=str(payload.get("trade_id") or ""),
            qty=_dec(payload.get("last_qty")) or Decimal(0),
            px=_dec(payload.get("last_px")) or Decimal(0),
            ts_event=ts,
            commission=commission,
            commission_currency=commission_ccy or payload.get("currency"),
        )
        # The projection owns what a fill does to an order — the running
        # ``filled_qty``, ``avg_px`` and terminality are all derived from the
        # full set of executions, never added to what is already stored.
        order = projection.add_fill(
            client_order_id,
            fill,
            updated_at=ts,
            venue_order_id=venue_order_id,
            reason=reason,
        )
        if order is None:
            # A fill this gateway has already folded. Delivery is at-least-once
            # (docs/bridge.md), so a node restart replaying one is expected;
            # appending a second event for it would hand NoFX a duplicate the
            # contract's `seq` could not help it dedupe, because the seq would
            # genuinely be new.
            return None
    else:
        changes: dict[str, Any] = {"status": ORDER_STATUS[kind], "updated_at": ts}
        if venue_order_id:
            changes["venue_order_id"] = venue_order_id
        if reason:
            changes["reason"] = reason
        order = projection.amend_order(client_order_id, **changes)
        assert order is not None  # the unknown-order case returned above

    event: dict[str, Any] = {
        "type": "fill" if fill is not None else "order",
        "account_id": order.account_id,
        "ts_event": ts,
        "order": order.contract(),
    }
    if fill is not None:
        event["fill"] = fill.contract()
    return projection.append_event(event)


def admitted_order(
    *,
    client_order_id: str,
    account_id: str,
    node: str,
    symbol: str,
    side: str,
    qty: Decimal,
    order_type: str,
    now: float,
    limit_px: Decimal | None = None,
    time_in_force: str | None = None,
    fingerprint: str = "",
) -> OrderRow:
    """The row the gateway writes at admission, before any node has seen it.

    ``admitted`` is a gateway state, not a venue state: the command is on
    ``algobots:cmd:<node>`` and nothing has been submitted anywhere yet.
    """
    stamp = iso(now)
    return OrderRow(
        client_order_id=client_order_id,
        account_id=account_id,
        symbol=symbol,
        side=side,
        qty=qty,
        order_type=order_type,
        status="admitted",
        submitted_at=stamp,
        updated_at=stamp,
        limit_px=limit_px,
        time_in_force=time_in_force,
        fingerprint=fingerprint,
        node=node,
    )


__all__ = [
    "HEARTBEAT",
    "ORDER_STATUS",
    "POSITION_SIDES",
    "SIDES",
    "account_contract",
    "admitted_order",
    "ingest",
    "normalize",
]
