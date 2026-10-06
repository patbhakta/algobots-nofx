"""Delta-vs-holdings order planner — TargetWeights in, OrderPlan out.

Pure, deterministic, dry-run: :func:`plan_orders` performs no network I/O
and emits a serializable plan artifact. Policy:

- Delta = target − current. Targets ≤ 0 or absent from the target set are
  liquidated (sell-to-zero); the planner never enters shorts, and a sell
  never exceeds current holdings.
- Symbols with unknown price or instrument state produce no order and are
  listed as ``unknown`` in the artifact.
- Market closed → the full plan artifact is still produced, annotated
  ``dispatch_at: next_open``; nothing dispatches.
- Orders pass through the S1.2 risk rail when a :class:`RiskGate` is
  supplied: a clamped entry surfaces the clamp in the artifact, and the
  gate writes its ClampEvent row via the existing sink.
"""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_DOWN, Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from algobots.execution.governor import GovernorResult, TurnoverGovernor
from algobots.execution.quantity import QTY_QUANT, coerce_decimal
from algobots.risk.audit import RiskGate

__all__ = [
    "AccountState",
    "ClampAnnotation",
    "DisciplineAnnotations",
    "GatedOut",
    "MarketState",
    "OrderPlan",
    "PlannedOrder",
    "PlannerConfig",
    "Position",
    "plan_orders",
]


class Position(BaseModel):
    """One held symbol. ``quantity`` is signed (negative = short)."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    quantity: Decimal
    price: Decimal | None = None
    tradable: bool = True

    @property
    def known(self) -> bool:
        """True when instrument state and price are both usable for sizing."""
        return self.tradable and self.price is not None


class MarketState(BaseModel):
    """Market clock plus the quote touch used by the discipline layer."""

    model_config = ConfigDict(extra="forbid")

    is_open: bool
    next_open: str | None = None
    bid: Decimal | None = None
    ask: Decimal | None = None
    upstream_available: bool = True


class AccountState(BaseModel):
    """Signed per-symbol position quantities as the venue reports them."""

    model_config = ConfigDict(extra="forbid")

    positions: dict[str, Decimal] = Field(default_factory=dict)


class ClampAnnotation(BaseModel):
    """A risk-rail clamp surfaced on the order it shrank."""

    model_config = ConfigDict(extra="forbid")

    limit: str
    before: Decimal
    after: Decimal


class PlannedOrder(BaseModel):
    """One planned order. ``notional`` is signed: positive buy, negative sell."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    side: Literal["buy", "sell"]
    quantity: Decimal
    notional: Decimal
    intent: Literal["entry", "exit"]
    clamp: ClampAnnotation | None = None


class GatedOut(BaseModel):
    """An order the risk gate denied outright, with the gate's reason."""

    model_config = ConfigDict(extra="forbid")

    symbol: str
    reason: str


class PlannerConfig(BaseModel):
    """Money rails for one planning pass — caps are required, explicit."""

    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    nav: Decimal = Field(gt=0)
    turnover_cap: Decimal = Field(gt=0)
    risk_gate: RiskGate | None = None


class DisciplineAnnotations(BaseModel):
    """Static execution-discipline policy carried on every artifact."""

    model_config = ConfigDict(extra="forbid")

    entry_order_type: Literal["post_only_limit"] = "post_only_limit"
    exit_order_type: Literal["ioc"] = "ioc"
    exit_reduce_only: bool = True
    one_order_per_tick: bool = True
    newest_plan_supersedes: bool = True
    hold_pulls_stale: bool = True


class OrderPlan(BaseModel):
    """Serializable dry-run plan artifact."""

    model_config = ConfigDict(extra="forbid")

    inputs_hash: str
    market_closed: bool
    dispatch_at: str | None = None
    projected_turnover: Decimal
    turnover: Decimal
    scale_factor: Decimal
    orders: list[PlannedOrder]
    unknown: list[str]
    gated_out: list[GatedOut]
    discipline: DisciplineAnnotations


def plan_orders(
    target_weights: dict[str, Decimal],
    holdings: dict[str, Position],
    market_state: MarketState,
    config: PlannerConfig,
) -> OrderPlan:
    """Plan delta-vs-holdings orders. Zero network calls, zero dispatch."""
    inputs_hash = _inputs_hash(target_weights, holdings, market_state, config)

    desired: dict[str, Decimal] = {}
    current: dict[str, Decimal] = {}
    prices: dict[str, Decimal] = {}
    unknown: list[str] = []
    for symbol in sorted(set(target_weights) | set(holdings)):
        position = holdings.get(symbol, Position(symbol=symbol, quantity=Decimal(0)))
        current[symbol] = position.quantity
        if not position.known:
            unknown.append(symbol)
            continue
        prices[symbol] = position.price
        weight = target_weights.get(symbol)
        if weight is None or coerce_decimal(weight) <= 0:
            desired[symbol] = Decimal(0)
        else:
            desired[symbol] = (
                (coerce_decimal(weight) * config.nav) / position.price
            ).quantize(QTY_QUANT, ROUND_DOWN)

    orders = _delta_orders(desired, current, prices)
    governor = TurnoverGovernor(turnover_cap=config.turnover_cap, nav=config.nav)
    governed = governor.apply(orders, current=current, prices=prices)
    final_orders, gated_out = _risk_gate_pass(governed, current, prices, config)

    market_closed = not market_state.is_open
    return OrderPlan(
        inputs_hash=inputs_hash,
        market_closed=market_closed,
        dispatch_at=market_state.next_open if market_closed else None,
        projected_turnover=governed.projected_turnover,
        turnover=governed.turnover,
        scale_factor=governed.scale_factor,
        orders=final_orders,
        unknown=unknown,
        gated_out=gated_out,
        discipline=DisciplineAnnotations(),
    )


def _delta_orders(
    desired: dict[str, Decimal],
    current: dict[str, Decimal],
    prices: dict[str, Decimal],
) -> list[PlannedOrder]:
    orders: list[PlannedOrder] = []
    for symbol in sorted(desired):
        target = desired[symbol]
        held = current[symbol]
        delta = target - held
        if held > 0 and delta < -held:
            delta = -held
        if held < 0 and delta > -held:
            delta = -held
        if abs(delta) < QTY_QUANT:
            continue
        reducing = (held > 0 and delta < 0) or (held < 0 and delta > 0)
        orders.append(
            PlannedOrder(
                symbol=symbol,
                side="buy" if delta > 0 else "sell",
                quantity=abs(delta),
                notional=delta * prices[symbol],
                intent="exit" if reducing else "entry",
            )
        )
    return orders


def _risk_gate_pass(
    governed: GovernorResult,
    current: dict[str, Decimal],
    prices: dict[str, Decimal],
    config: PlannerConfig,
) -> tuple[list[PlannedOrder], list[GatedOut]]:
    if config.risk_gate is None:
        return governed.orders, []
    final_orders: list[PlannedOrder] = []
    gated_out: list[GatedOut] = []
    for order in governed.orders:
        decision = config.risk_gate.approve_order(
            kind=order.intent,
            value=abs(order.notional),
            ticker=order.symbol,
        )
        if not decision.allowed:
            gated_out.append(
                GatedOut(symbol=order.symbol, reason=decision.reason or "denied")
            )
            continue
        if (
            order.intent == "entry"
            and decision.approved_value is not None
            and decision.approved_value < abs(order.notional)
        ):
            before = abs(order.notional)
            after = decision.approved_value
            order = order.model_copy(
                update={
                    "quantity": (after / prices[order.symbol]).quantize(
                        QTY_QUANT, ROUND_DOWN
                    ),
                    "notional": after if order.side == "buy" else -after,
                    "clamp": ClampAnnotation(
                        limit="max_order_value", before=before, after=after
                    ),
                }
            )
        final_orders.append(order)
    return final_orders, gated_out


def _inputs_hash(
    target_weights: dict[str, Decimal],
    holdings: dict[str, Position],
    market_state: MarketState,
    config: PlannerConfig,
) -> str:
    payload = {
        "target_weights": {
            symbol: str(coerce_decimal(weight))
            for symbol, weight in sorted(target_weights.items())
        },
        "holdings": [
            {
                "symbol": position.symbol,
                "quantity": str(position.quantity),
                "price": None if position.price is None else str(position.price),
                "tradable": position.tradable,
            }
            for position in sorted(holdings.values(), key=lambda p: p.symbol)
        ],
        "market_state": {
            "is_open": market_state.is_open,
            "next_open": market_state.next_open,
            "bid": None if market_state.bid is None else str(market_state.bid),
            "ask": None if market_state.ask is None else str(market_state.ask),
            "upstream_available": market_state.upstream_available,
        },
        "nav": str(config.nav),
        "turnover_cap": str(config.turnover_cap),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
