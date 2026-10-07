"""Daily loss calculation with account timezone and clean components (A08).

The trading day boundary is the account's IANA timezone (``RiskPolicyVersion.
timezone``) — a loss cap that resets at UTC midnight while the account trades
Asia hours would be wrong. The calculation is explicit about its components:

- ``equity_reference``   start-of-day equity (the reference the cap measures
                         against — deposits and withdrawals ADJUST it, they
                         are never gains or losses);
- ``realized``           settled cash P&L of the trading day (fees included);
- ``unrealized``         open positions marked at the last known mark, tagged
                         with that mark's quality — a stale or indicative mark
                         is reported, never silently trusted.

``DailyLossReport.tripped`` compares against the policy's ``max_daily_loss``;
``loss >= cap`` trips (a loss equal to the cap has consumed the whole
envelope, matching ``envelopes.RiskEnvelope``'s convention).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from algobots.contracts.risk import MarkQuality

__all__ = [
    "DailyLossInput",
    "DailyLossReport",
    "MarkedPosition",
    "daily_loss_report",
    "trading_day_bounds",
]


def trading_day_bounds(timezone: str, now: datetime) -> tuple[datetime, datetime]:
    """[start, start + 24h) of ``now``'s trading day, in UTC.

    The local calendar day in the account timezone is the trading day: the
    boundary is local midnight converted back to UTC, so DST shifts move the
    UTC instant but never the local day.
    """
    local = now.astimezone(ZoneInfo(timezone))
    start_local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    return start_local.astimezone(UTC), start_local.astimezone(UTC) + timedelta(days=1)


class MarkedPosition(BaseModel):
    """One open position marked for the unrealized component."""

    model_config = ConfigDict(extra="forbid")

    instrument_id: str
    quantity: Decimal  # signed: negative = short
    mark_price: Decimal = Field(gt=0)
    mark_quality: MarkQuality = "STALE_CACHE"
    #: Cost basis used for the unrealized P&L of the position.
    average_entry_price: Decimal = Field(gt=0)


class DailyLossInput(BaseModel):
    """Everything the daily loss needs, stated once."""

    model_config = ConfigDict(extra="forbid")

    equity_reference: Decimal
    realized_pnl: Decimal = Decimal(0)
    positions: tuple[MarkedPosition, ...] = ()
    deposits: Decimal = Decimal(0)  # positive cash INTO the account today
    withdrawals: Decimal = Decimal(0)  # positive cash OUT of the account today
    cash_balance: Decimal = Decimal(0)


class DailyLossReport(BaseModel):
    """The components, the adjustment, the verdict — nothing hidden."""

    model_config = ConfigDict(extra="forbid")

    trading_day_start: datetime
    trading_day_end: datetime
    equity_reference: Decimal
    realized: Decimal
    unrealized: Decimal
    deposits: Decimal
    withdrawals: Decimal
    #: equity_reference adjusted so transfers are not counted as P&L.
    adjusted_reference: Decimal
    daily_pnl: Decimal
    worst_mark_quality: MarkQuality | None = None
    all_marks_fresh: bool = True
    max_daily_loss: Decimal | None = None

    @property
    def loss(self) -> Decimal:
        return -self.daily_pnl

    @property
    def tripped(self) -> bool:
        return self.max_daily_loss is not None and self.loss >= self.max_daily_loss


_FRESH_QUALITIES = frozenset({"REALTIME", "DELAYED"})


def daily_loss_report(
    *,
    timezone: str,
    now: datetime,
    data: DailyLossInput,
    max_daily_loss: Decimal | None = None,
) -> DailyLossReport:
    """Deterministic daily loss report for ``now``'s trading day."""
    start, end = trading_day_bounds(timezone, now)
    unrealized = sum(
        (p.mark_price - p.average_entry_price) * p.quantity for p in data.positions
    )
    qualities = [p.mark_quality for p in data.positions if p.quantity != 0]
    worst = None
    if qualities:
        rank = {q: i for i, q in enumerate(("REALTIME", "DELAYED", "STALE_CACHE", "INDICATIVE"))}
        worst = max(qualities, key=lambda q: rank[q])
    adjusted_reference = data.equity_reference + data.deposits - data.withdrawals
    daily_pnl = data.realized_pnl + unrealized
    return DailyLossReport(
        trading_day_start=start,
        trading_day_end=end,
        equity_reference=data.equity_reference,
        realized=data.realized_pnl,
        unrealized=unrealized,
        deposits=data.deposits,
        withdrawals=data.withdrawals,
        adjusted_reference=adjusted_reference,
        daily_pnl=daily_pnl,
        worst_mark_quality=worst,
        all_marks_fresh=all(q in _FRESH_QUALITIES for q in qualities),
        max_daily_loss=max_daily_loss,
    )
