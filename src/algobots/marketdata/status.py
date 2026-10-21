"""Watchlist status surface: market state, data timestamps, precision (A05 demo).

One watchlist spans asset classes (an equity next to spot crypto): each entry
reports the session state at ``as_of``, the best-precedence entitled
snapshot's three timestamps, its age/freshness, and the decimal precision the
instrument's tick/lot configure. This powers ``/market-data/status`` and the
A05 demo; ``demo/bars.py``/``quality.py`` remain dashboard read-side
surfaces and are untouched.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from algobots.contracts.instrument import Instrument
from algobots.instruments.calendar import SessionState, market_session
from algobots.instruments.registry import InstrumentRegistry, default_registry
from algobots.marketdata.freshness import FreshnessPolicy, assess
from algobots.marketdata.replay import ReplayFeed

__all__ = ["InstrumentStatus", "watchlist_status"]


@dataclass(frozen=True)
class InstrumentStatus:
    instrument_id: str
    venue: str
    product: str
    symbol: str
    quote_currency: str
    market_open: bool
    market_reason: str
    last_event_time: str | None
    last_available_time: str | None
    last_receive_time: str | None
    source: str | None
    sequence: int | None
    age_seconds: int | None
    fresh: bool
    eligible: bool
    reasons: tuple[str, ...]
    price_precision: int
    quantity_precision: int


def _status(
    instrument: Instrument,
    feed: ReplayFeed,
    as_of: datetime,
    policy: FreshnessPolicy | None,
) -> InstrumentStatus:
    session: SessionState = market_session(instrument.calendar, instrument.timezone, as_of)
    snapshot = feed.latest(instrument.instrument_id, as_of)
    assessment = assess(instrument, snapshot, as_of, policy)
    return InstrumentStatus(
        instrument_id=instrument.instrument_id,
        venue=instrument.venue,
        product=str(instrument.product),
        symbol=instrument.symbol,
        quote_currency=instrument.quote_currency,
        market_open=session.open,
        market_reason=session.reason,
        last_event_time=snapshot.event_time.isoformat() if snapshot else None,
        last_available_time=snapshot.available_time.isoformat() if snapshot else None,
        last_receive_time=snapshot.receive_time.isoformat() if snapshot else None,
        source=snapshot.source if snapshot else None,
        sequence=snapshot.sequence if snapshot else None,
        age_seconds=assessment.age_seconds,
        fresh=assessment.fresh,
        eligible=assessment.eligible,
        reasons=assessment.reasons,
        price_precision=instrument.price_decimals(),
        quantity_precision=instrument.quantity_decimals(),
    )


def watchlist_status(
    instrument_ids: tuple[str, ...] | None = None,
    feed: ReplayFeed | None = None,
    as_of: datetime | None = None,
    registry: InstrumentRegistry | None = None,
    policy: FreshnessPolicy | None = None,
) -> list[dict]:
    """Status rows for one mixed-asset-class watchlist, as JSON-ready dicts."""
    registry = registry or default_registry()
    ids = instrument_ids or tuple(i.instrument_id for i in registry.list())
    if feed is None:
        from algobots.marketdata.recorded import load_recording

        feed = ReplayFeed(load_recording())
    # Default as-of is the recording's latest available time, not wall clock:
    # read-only surfaces stay deterministic over recorded data.
    when = as_of if as_of is not None else feed.latest_available()
    if when is None:
        when = datetime.now(UTC)
    if when.utcoffset() is None:
        raise ValueError("as_of must be offset-aware")
    rows = [_status(registry.get(i), feed, when, policy) for i in ids]
    return [dict(asdict(row), reasons=list(row.reasons)) for row in rows]
