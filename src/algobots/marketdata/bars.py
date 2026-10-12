"""Completed-bar semantics and gap detection (A05 item 3).

Bars are built from snapshot *event times* in the instrument's timezone, and a
bar is emitted only when a tick from a **later** interval arrives — the
current, incomplete bar is never emitted (acceptance case 3). Missing
intervals between completed bars are counted as ``gap_before`` on the next
emitted bar; an interval with no ticks simply produces no bar.

This supersedes the *shape* (not the file) of A06's deterministic synthetic
stream in ``engine/workers/fixture.py``, which models no event-time or
sequence semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from algobots.contracts.instrument import Instrument
from algobots.contracts.marketdata import MarketSnapshot

__all__ = ["Bar", "BarBuilder", "BarStreamError"]


class BarStreamError(ValueError):
    """The snapshot stream violates bar-building invariants."""


@dataclass(frozen=True)
class Bar:
    instrument_id: str
    interval_seconds: int
    open_ts: datetime  # interval start, UTC
    close_ts: datetime  # interval end (exclusive), UTC — a completed bar's label
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    ticks: int
    gap_before: int  # completed intervals with no ticks since the previous completed bar


class BarBuilder:
    """One instrument's quote-to-bar reducer with completed-bar semantics."""

    def __init__(self, instrument: Instrument, interval_seconds: int) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self._instrument = instrument
        self._interval = timedelta(seconds=interval_seconds)
        self._interval_seconds = interval_seconds
        self._tz = ZoneInfo(instrument.timezone)
        self._current: Bar | None = None
        self._current_closes: list[Decimal] | None = None
        self._last_event: datetime | None = None

    def _bucket_start(self, at: datetime) -> datetime:
        local = at.astimezone(self._tz)
        epoch = local.timestamp()
        bucket_local = datetime.fromtimestamp(
            epoch - (epoch % self._interval_seconds), tz=self._tz
        )
        return bucket_local.astimezone(UTC)

    def _mid(self, snap: MarketSnapshot) -> Decimal:
        if snap.bid is not None and snap.ask is not None:
            return (snap.bid.amount + snap.ask.amount) / 2
        if snap.last is not None:
            return snap.last.amount
        if snap.bid is not None:
            return snap.bid.amount
        assert snap.ask is not None
        return snap.ask.amount

    def on_snapshot(self, snap: MarketSnapshot) -> Bar | None:
        """Ingest one snapshot; returns a bar only when a *previous* bar completes."""
        if snap.instrument_id != self._instrument.instrument_id:
            raise BarStreamError(
                f"bar builder for {self._instrument.instrument_id} got {snap.instrument_id}"
            )
        event = snap.event_time.astimezone(UTC)
        if self._last_event is not None and event < self._last_event:
            raise BarStreamError(
                "event times must be non-decreasing; use replay order, not wall arrival"
            )
        self._last_event = event
        price = self._mid(snap)
        size = snap.last_size.value if snap.last_size is not None else (
            snap.bid_size.value if snap.bid_size is not None else (
                snap.ask_size.value if snap.ask_size is not None else Decimal(0)
            )
        )

        start = self._bucket_start(event)
        completed: Bar | None = None
        if self._current is None:
            self._current = self._open_bar(start, price, size)
            self._current_closes = [price]
            return None
        if start == self._current.open_ts:
            self._current = self._extend(self._current, price, size)
            self._current_closes.append(price)
            return None
        if start > self._current.open_ts:
            completed = self._current  # a later-interval tick closes the previous bar
            gap = self._gap_between(completed.close_ts, start)
            self._current = self._open_bar(start, price, size, gap_before=gap)
            self._current_closes = [price]
            return completed
        raise BarStreamError(
            f"snapshot event {event.isoformat()} precedes the open bar interval"
        )

    def _open_bar(
        self, start: datetime, price: Decimal, size: Decimal, gap_before: int = 0
    ) -> Bar:
        return Bar(
            instrument_id=self._instrument.instrument_id,
            interval_seconds=self._interval_seconds,
            open_ts=start,
            close_ts=start + self._interval,
            open=price,
            high=price,
            low=price,
            close=price,
            volume=size,
            ticks=1,
            gap_before=gap_before,
        )

    @staticmethod
    def _extend(bar: Bar, price: Decimal, size: Decimal) -> Bar:
        return Bar(
            instrument_id=bar.instrument_id,
            interval_seconds=bar.interval_seconds,
            open_ts=bar.open_ts,
            close_ts=bar.close_ts,
            open=bar.open,
            high=max(bar.high, price),
            low=min(bar.low, price),
            close=price,
            volume=bar.volume + size,
            ticks=bar.ticks + 1,
            gap_before=bar.gap_before,
        )

    def _gap_between(self, previous_close: datetime, next_start: datetime) -> int:
        delta = next_start - previous_close
        return max(0, int(delta / self._interval))

    @property
    def current_incomplete(self) -> Bar | None:
        """The forming bar — never to be consumed as completed data."""
        return self._current

    @property
    def last_event_time(self) -> datetime | None:
        """The newest event time ingested so far (correlation/replay guard)."""
        return self._last_event

    def closes(self) -> list[Decimal]:
        """Closes of the current forming bar (feature warmup reads completed bars only)."""
        return list(self._current_closes or [])
