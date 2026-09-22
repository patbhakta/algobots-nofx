"""jev-trade execution mechanics — venue-agnostic policy port.

Port of the jev-trade plan/trader mechanics studied in ALG-3075 (upstream
``plan.ts`` / ``trader.ts``):

- entries → post-only limit orders priced one tick inside the touch
- exits / reductions → IOC with ``reduceOnly=true``
- state unknown or upstream unavailable → hold
- at most one order per tick, via a sequenced send queue where the newest
  plan supersedes and pulls stale queued orders (hold pulls stale quotes)

Venue adapters are out of scope: :meth:`ExecutionDiscipline.tick` only
decides what would be sent next, or that nothing may be sent (hold).

Entry pricing: a buy posts at ``ask − tick_size`` and a sell at
``bid + tick_size`` — one tick inside the far quote, which can never cross
the touch, so the post-only constraint is satisfiable by construction.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict

from algobots.execution.quantity import coerce_decimal

if TYPE_CHECKING:
    from algobots.execution.planner import (
        AccountState,
        MarketState,
        OrderPlan,
        PlannedOrder,
    )

__all__ = ["ExecutionDiscipline", "OrderInstruction"]


class OrderInstruction(BaseModel):
    """The one instruction a tick may send, fully priced and flagged."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    order_type: Literal["post_only_limit", "ioc"]
    limit_price: Decimal | None = None
    reduce_only: bool = False
    plan_hash: str | None = None


class ExecutionDiscipline:
    """Sequenced, superseding, one-order-per-tick dispatch policy."""

    def __init__(self, *, tick_size: Decimal) -> None:
        self.tick_size = coerce_decimal(tick_size)
        if self.tick_size <= 0:
            raise ValueError("tick_size must be > 0")
        self._queue: list[PlannedOrder] = []
        self._plan_hash: str | None = None

    def tick(
        self,
        plan: OrderPlan | None,
        market_state: MarketState,
        account_state: AccountState,
    ) -> OrderInstruction | None:
        """Return at most one instruction for this tick, or None (hold)."""
        if (
            not market_state.is_open
            or plan is None
            or not plan.orders
            or not market_state.upstream_available
            or market_state.bid is None
            or market_state.ask is None
        ):
            return self._hold()
        if plan.inputs_hash != self._plan_hash:
            self._queue = list(plan.orders)
            self._plan_hash = plan.inputs_hash
        if not self._queue:
            return None
        order = self._queue.pop(0)
        if order.intent == "exit":
            return self._exit_instruction(order, account_state)
        return self._entry_instruction(order, market_state)

    def _hold(self) -> None:
        """Pull stale queued orders — a hold supersedes everything queued."""
        self._queue = []
        self._plan_hash = None
        return None

    def _exit_instruction(
        self, order: PlannedOrder, account_state: AccountState
    ) -> OrderInstruction | None:
        held = account_state.positions.get(order.symbol)
        if held is None or held == 0:
            return None
        return OrderInstruction(
            symbol=order.symbol,
            side=order.side,
            quantity=min(order.quantity, abs(held)),
            order_type="ioc",
            reduce_only=True,
            plan_hash=self._plan_hash,
        )

    def _entry_instruction(
        self, order: PlannedOrder, market_state: MarketState
    ) -> OrderInstruction:
        if order.side == "buy":
            limit_price = market_state.ask - self.tick_size
        else:
            limit_price = market_state.bid + self.tick_size
        return OrderInstruction(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            order_type="post_only_limit",
            limit_price=limit_price,
            reduce_only=False,
            plan_hash=self._plan_hash,
        )
