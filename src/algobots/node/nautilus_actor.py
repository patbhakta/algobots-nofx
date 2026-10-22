"""Binding :class:`~algobots.node.command_actor.CommandActor` to a real node.

Everything Nautilus-specific in P1.3 is in this file, and there is not much of
it: translate a :class:`~algobots.node.commands.SubmitOrder` into an order the
engine's factory builds, hand it to ``Strategy.submit_order``, and answer
"does this client order id exist?" from the engine's cache.

Three things here are load-bearing, and all three are about the client order id:

1. **``client_order_id`` is passed to the factory explicitly.** Nautilus will
   happily generate one, and every other strategy in this repo lets it — see
   ``PaperWorker``. P1.3 may not: a generated id is not the caller's key, and
   dedupe at the venue would be lost the moment the engine chose its own.
2. **``cache.order`` is the dedupe authority.** The cache is reconciled against
   the venue when the node starts (``reconciled`` on the heartbeat is the same
   fact the gateway's fitness check reads), so an id that survived a restart is
   still found. A set in this process would not have survived it.
3. **Quantities and prices go through the instrument.** ``instrument.make_qty``
   and ``make_price`` apply the venue's own precision. Rounding a decimal here
   would mean the gateway reported a qty the venue never saw.

Nautilus is imported inside the methods that need it, so importing this module
costs nothing and ``algobots.node.command_actor`` stays importable — and
testable — in the API process and in CI, where ``nautilus_trader`` is absent
(it lives in the ``workers`` extra; CI installs ``dev``).

Pinned to ``2.0.0rc6`` (roadmap rule 5) and exercised on it by
:mod:`algobots.node.paper_node` (ALG-3405). The API this module touches is small
and deliberately so: ``order_factory.market``/``limit``, ``submit_order``,
``cancel_order`` and ``cache.order``/``cache.instrument``. rc6 moved every
model type to ``nautilus_trader.model`` and cancels by ``ClientOrderId``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from algobots.node.commands import SubmitOrder


class InstrumentNotLoaded(RuntimeError):
    """The node has no instrument for this symbol *yet*.

    Raised rather than refused, which matters for the stream: a refusal is
    acknowledged and dropped, but this is plausibly transient — the node may
    still be loading instruments — so the entry stays pending and is
    redelivered. A command must not be discarded because it arrived early.
    """


@dataclass
class NautilusExecution:
    """:class:`~algobots.node.command_actor.ExecutionSurface` over a Strategy.

    A ``Strategy`` rather than a bare ``Actor``: only a strategy has the
    ``order_factory`` and the ``submit_order``/``cancel_order`` methods that
    ADR 0001 requires every order to pass through.
    """

    strategy: Any  # nautilus_trader.trading.strategy.Strategy

    def status(self, client_order_id: str) -> str | None:
        """The engine's own answer, as an ``OrderStatus`` name."""
        from nautilus_trader.model import ClientOrderId

        order = self.strategy.cache.order(ClientOrderId(client_order_id))
        if order is None:
            return None
        status = order.status
        # OrderStatus is an enum in rc6; `.name` is the stable spelling the
        # actor's TERMINAL / IN_FLIGHT_CANCEL sets are written against.
        return getattr(status, "name", str(status))

    def submit(self, order: SubmitOrder) -> None:
        from nautilus_trader.model import ClientOrderId, InstrumentId, OrderSide, TimeInForce

        instrument_id = InstrumentId.from_str(order.symbol)
        instrument = self.strategy.cache.instrument(instrument_id)
        if instrument is None:
            raise InstrumentNotLoaded(
                f"node has no instrument {order.symbol!r} — cannot size the order"
            )

        side = OrderSide.BUY if order.side == "buy" else OrderSide.SELL
        common = {
            "instrument_id": instrument_id,
            "order_side": side,
            "quantity": instrument.make_qty(order.qty),
            # The caller's idempotency key, verbatim. This is the line the
            # whole sprint is about.
            "client_order_id": ClientOrderId(order.client_order_id),
            # rc6's enums are pyo3 classes: attribute lookup, not ``Enum[name]``.
            "time_in_force": getattr(TimeInForce, order.time_in_force.upper()),
        }
        if order.reduce_only:
            common["reduce_only"] = True

        if order.order_type == "limit":
            assert order.limit_px is not None  # commands.parse guarantees it
            built = self.strategy.order_factory.limit(
                price=instrument.make_price(order.limit_px), **common
            )
        else:
            # A market order has no time_in_force beyond the venue's immediate
            # semantics in some adapters; Nautilus still accepts GTC here and
            # normalises it, so the command's value is passed through unchanged.
            built = self.strategy.order_factory.market(**common)

        self.strategy.submit_order(built)

    def cancel(self, client_order_id: str) -> None:
        from nautilus_trader.model import ClientOrderId

        order = self.strategy.cache.order(ClientOrderId(client_order_id))
        if order is None:
            # The actor checked status() first, so this is a genuine race (the
            # order left the cache between the two calls). Raising lets the
            # entry be redelivered rather than silently dropping a cancel.
            raise RuntimeError(f"order {client_order_id} vanished from the cache before cancel")
        # rc6 cancels by id, not by order object (1.x took the order).
        self.strategy.cancel_order(order.client_order_id)


__all__ = ["InstrumentNotLoaded", "NautilusExecution"]
