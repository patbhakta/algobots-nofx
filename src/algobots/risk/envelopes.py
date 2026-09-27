"""Per-deployment risk envelopes — explicit money caps, no silent defaults.

An envelope is the money rail for a single deployment: the maximum notional
of any one entry order and the maximum daily loss the deployment may incur
before new entries are blocked. Both caps are REQUIRED ``Decimal`` fields —
an envelope missing an explicit cap fails validation. Money rails never get
silent defaults.

Exits are privileged (see ``breakers.RateBreakers`` and ``audit.RiskGate``):
an exhausted envelope blocks entries, never exits.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["DailyLossCheck", "OrderValueCheck", "RiskEnvelope"]


class RiskEnvelope(BaseModel):
    """Per-deployment money envelope. Caps are required, explicit, Decimal."""

    model_config = ConfigDict(extra="forbid")

    max_order_value: Decimal = Field(
        gt=0,
        description="Hard cap on any single ENTRY order's notional value (quote currency).",
    )
    max_daily_loss: Decimal = Field(
        gt=0,
        description=(
            "Hard cap on a deployment's daily loss (realized + unrealized). "
            "When loss >= cap the envelope is exhausted: new entries are "
            "blocked, exits stay privileged."
        ),
    )

    def clamp_order_value(self, requested: Decimal) -> OrderValueCheck:
        """Clamp a proposed entry notional to ``max_order_value``.

        Clamping only ever shrinks |notional|; the sign (long/short) is
        preserved. Exits are not routed through this method — they are
        privileged and pass at their requested size.
        """
        requested = _coerce_decimal(requested)
        cap = self.max_order_value
        if abs(requested) <= cap:
            return OrderValueCheck(requested=requested, approved=requested, fired=False)
        approved = cap if requested > 0 else -cap
        return OrderValueCheck(requested=requested, approved=approved, fired=True)

    def check_daily_loss(self, daily_pnl: Decimal) -> DailyLossCheck:
        """Check signed daily P&L against ``max_daily_loss``.

        Trips deterministically at loss >= cap: a loss equal to the cap has
        consumed the whole envelope (conservative on money rails).
        ``daily_pnl`` is signed — negative is loss.
        """
        daily_pnl = _coerce_decimal(daily_pnl)
        loss = -daily_pnl
        return DailyLossCheck(
            daily_pnl=daily_pnl,
            max_daily_loss=self.max_daily_loss,
            tripped=loss >= self.max_daily_loss,
        )


class OrderValueCheck(BaseModel):
    """Result of clamping one order's notional against ``max_order_value``."""

    model_config = ConfigDict(extra="forbid")

    requested: Decimal
    approved: Decimal
    fired: bool


class DailyLossCheck(BaseModel):
    """Result of checking daily-loss state against ``max_daily_loss``."""

    model_config = ConfigDict(extra="forbid")

    daily_pnl: Decimal
    max_daily_loss: Decimal
    tripped: bool


def _coerce_decimal(value: Decimal | int | str) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))
