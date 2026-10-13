"""A08 daily loss: timezone boundary, components, transfer adjustments."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from algobots.risk.daily import (
    DailyLossInput,
    MarkedPosition,
    daily_loss_report,
    trading_day_bounds,
)

D = Decimal


def test_trading_day_boundary_follows_account_timezone():
    # 2026-10-07 23:30 UTC is already 2026-10-08 in Tokyo (UTC+9).
    now = datetime(2026, 10, 7, 23, 30, tzinfo=UTC)
    start, end = trading_day_bounds("Asia/Tokyo", now)
    assert (start.hour, start.day) == (15, 7)  # 00:00 JST Oct 8 == 15:00 UTC Oct 7
    assert start == datetime(2026, 10, 7, 15, 0, tzinfo=UTC)
    assert (end - start).total_seconds() == 86400
    # same instant in New York is still Oct 7 locally
    start_ny, _ = trading_day_bounds("America/New_York", now)
    assert start_ny == datetime(2026, 10, 7, 4, 0, tzinfo=UTC)


def test_realized_plus_unrealized_components():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    report = daily_loss_report(
        timezone="UTC",
        now=now,
        data=DailyLossInput(
            equity_reference=D("10000"),
            realized_pnl=D("-150"),
            positions=(
                MarkedPosition(
                    instrument_id="KXA8.DEMO",
                    quantity=D("10"),
                    mark_price=D("92"),
                    mark_quality="REALTIME",
                    average_entry_price=D("100"),
                ),
            ),
        ),
        max_daily_loss=D("200"),
    )
    assert report.realized == D("-150")
    assert report.unrealized == D("-80")
    assert report.daily_pnl == D("-230")
    assert report.loss == D("230")
    assert report.tripped  # 230 >= 200
    assert report.all_marks_fresh
    assert report.worst_mark_quality == "REALTIME"


def test_deposits_and_withdrawals_adjust_reference_not_pnl():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    report = daily_loss_report(
        timezone="UTC",
        now=now,
        data=DailyLossInput(
            equity_reference=D("10000"),
            realized_pnl=D("0"),
            deposits=D("2000"),  # cash in: NOT a gain
            withdrawals=D("500"),  # cash out: NOT a loss
        ),
        max_daily_loss=D("100"),
    )
    assert report.adjusted_reference == D("11500")
    assert report.daily_pnl == D("0"), "transfers must never look like P&L"
    assert not report.tripped


def test_stale_mark_quality_is_reported_never_trusted():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    report = daily_loss_report(
        timezone="UTC",
        now=now,
        data=DailyLossInput(
            equity_reference=D("10000"),
            realized_pnl=D("0"),
            positions=(
                MarkedPosition(
                    instrument_id="A",
                    quantity=D("1"),
                    mark_price=D("100"),
                    mark_quality="REALTIME",
                    average_entry_price=D("100"),
                ),
                MarkedPosition(
                    instrument_id="B",
                    quantity=D("2"),
                    mark_price=D("50"),
                    mark_quality="INDICATIVE",
                    average_entry_price=D("100"),
                ),
            ),
        ),
    )
    assert report.worst_mark_quality == "INDICATIVE"
    assert not report.all_marks_fresh
    assert report.daily_pnl == D("-100")  # computed, but flagged as stale-marked


def test_loss_equal_to_cap_trips():
    now = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)
    report = daily_loss_report(
        timezone="UTC",
        now=now,
        data=DailyLossInput(equity_reference=D("10000"), realized_pnl=D("-100")),
        max_daily_loss=D("100"),
    )
    assert report.tripped, "a loss equal to the cap consumed the whole envelope"
