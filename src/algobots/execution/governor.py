"""Turnover governor — scales the plan down, never rejects.

Turnover = Σ|order notional| / NAV. When the projected turnover of a plan
exceeds ``turnover_cap``, every order quantity is scaled by
``cap / projected_turnover`` and sells are re-clamped to current holdings.
The governor never rejects a plan: the worst case is a scale factor < 1,
recorded on the artifact.

``turnover_cap`` and ``nav`` are REQUIRED ``Decimal`` constructor args —
no silent defaults on money rails.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

from algobots.execution.quantity import QTY_QUANT, coerce_decimal

if TYPE_CHECKING:
    from algobots.execution.planner import PlannedOrder

__all__ = ["GovernorResult", "TurnoverGovernor"]


@dataclass(frozen=True)
class GovernorResult:
    """Post-governor orders plus the recorded turnover telemetry."""

    orders: list[PlannedOrder]
    projected_turnover: Decimal
    turnover: Decimal
    scale_factor: Decimal


class TurnoverGovernor:
    """Scales a plan to fit the turnover cap. Never rejects."""

    def __init__(self, *, turnover_cap: Decimal, nav: Decimal) -> None:
        self.turnover_cap = coerce_decimal(turnover_cap)
        self.nav = coerce_decimal(nav)
        if self.turnover_cap <= 0:
            raise ValueError("turnover_cap must be > 0")
        if self.nav <= 0:
            raise ValueError("nav must be > 0")

    def apply(
        self,
        orders: list[PlannedOrder],
        *,
        current: dict[str, Decimal],
        prices: dict[str, Decimal],
    ) -> GovernorResult:
        """Scale orders so Σ|notional| / NAV ≤ turnover_cap.

        Scaling multiplies every quantity by ``cap / projected_turnover``
        (rounded DOWN, so a quantity can never round above its holding),
        then re-clamps sells to current long holdings and covering buys to
        current short holdings. Quantities are first reconciled DOWN
        against their own notional (``|notional| / price``), so the cap
        holds for arbitrary inputs, even inconsistent ones. Orders scaled
        below the minimum tradable quantity are dropped.
        """
        projected = self._turnover(orders)
        if projected == 0 or projected <= self.turnover_cap:
            return GovernorResult(
                orders=list(orders),
                projected_turnover=projected,
                turnover=projected,
                scale_factor=Decimal(1),
            )
        scale = self.turnover_cap / projected
        scaled: list[PlannedOrder] = []
        for order in orders:
            price = prices[order.symbol]
            quantity = order.quantity
            if price > 0:
                implied = (abs(order.notional) / price).quantize(QTY_QUANT, ROUND_DOWN)
                quantity = min(quantity, implied)
            quantity = (quantity * scale).quantize(QTY_QUANT, ROUND_DOWN)
            held = current.get(order.symbol, Decimal(0))
            if order.side == "sell" and held > 0:
                quantity = min(quantity, held)
            if order.side == "buy" and held < 0:
                quantity = min(quantity, -held)
            if quantity < QTY_QUANT:
                continue
            notional = quantity * prices[order.symbol]
            scaled.append(
                order.model_copy(
                    update={
                        "quantity": quantity,
                        "notional": notional if order.side == "buy" else -notional,
                    }
                )
            )
        return GovernorResult(
            orders=scaled,
            projected_turnover=projected,
            turnover=self._turnover(scaled),
            scale_factor=scale,
        )

    def _turnover(self, orders: list[PlannedOrder]) -> Decimal:
        gross = sum((abs(order.notional) for order in orders), Decimal(0))
        return gross / self.nav
