"""A05 acceptance case 3 (calendar + freshness half): weekend equities, 24/7
crypto, DST transitions, stale quotes — eligibility/freshness matches fixture
expectations and fails closed."""

from __future__ import annotations

from datetime import UTC, datetime

from algobots.instruments import default_registry, is_open, market_session
from algobots.marketdata import FreshnessPolicy, ReplayFeed, assess, load_recording

AAPL = "XNAS:equity:AAPL"
BTC = "COINBASE:spot-crypto:BTC-USD"


def test_weekend_equity_session_closed():
    # Sat 2026-10-31 11:00 New York: market closed, explicit weekend reason.
    saturday = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
    session = market_session("XNAS", "America/New_York", saturday)
    assert not session.open
    assert session.reason.startswith("weekend:")
    assert not is_open("XNYS", "America/New_York", datetime(2026, 11, 1, 16, 0, tzinfo=UTC))


def test_equity_regular_session_boundaries():
    # Fri 2026-10-30: session 09:30-16:00 EDT == 13:30-20:00 UTC.
    ny = "America/New_York"
    assert not is_open("XNAS", ny, datetime(2026, 10, 30, 13, 29, 59, tzinfo=UTC))
    assert is_open("XNAS", ny, datetime(2026, 10, 30, 13, 30, 0, tzinfo=UTC))
    assert is_open("XNAS", ny, datetime(2026, 10, 30, 19, 59, 59, tzinfo=UTC))
    assert not is_open("XNAS", ny, datetime(2026, 10, 30, 20, 0, 0, tzinfo=UTC))


def test_dst_transitions_shift_the_utc_mapping_not_the_wall_clock():
    ny = "America/New_York"
    # Before fall-back (EDT, UTC-4): 09:30 local == 13:30 UTC.
    assert is_open("XNAS", ny, datetime(2026, 10, 30, 13, 30, tzinfo=UTC))
    # After fall-back Sun 2026-11-01 (EST, UTC-5): 09:30 local == 14:30 UTC.
    assert not is_open("XNAS", ny, datetime(2026, 11, 2, 13, 30, tzinfo=UTC))  # 08:30 local
    assert is_open("XNAS", ny, datetime(2026, 11, 2, 14, 30, tzinfo=UTC))  # 09:30 local


def test_crypto_trades_24x7_including_weekends():
    saturday = datetime(2026, 10, 31, 15, 0, tzinfo=UTC)
    sunday = datetime(2026, 11, 1, 3, 30, tzinfo=UTC)
    for at in (saturday, sunday):
        assert is_open("24x7", "UTC", at)


def test_unknown_calendar_and_naive_time_fail_closed():
    closed = market_session("MISSING", "UTC", datetime(2026, 10, 30, 15, 0, tzinfo=UTC))
    assert not closed.open and closed.reason.startswith("unknown-calendar:")
    import pytest

    with pytest.raises(ValueError):
        market_session("24x7", "UTC", datetime(2026, 10, 30, 15, 0))


def _feed() -> ReplayFeed:
    return ReplayFeed(load_recording())


def test_open_market_fresh_quote_is_eligible_and_fresh():
    registry = default_registry()
    feed = _feed()
    as_of = datetime(2026, 10, 30, 14, 5, 30, tzinfo=UTC)
    snapshot = feed.latest(AAPL, as_of)
    assert snapshot.sequence == 4  # 14:05:01 published
    verdict = assess(registry.get(AAPL), snapshot, as_of, FreshnessPolicy.defaults())
    assert verdict.eligible and verdict.fresh and verdict.ready_for_exposure()
    assert verdict.age_seconds == 29  # equity max age 60s


def test_weekend_equity_tick_is_fresh_but_not_eligible():
    registry = default_registry()
    feed = _feed()
    as_of = datetime(2026, 10, 31, 15, 0, 30, tzinfo=UTC)  # Saturday
    snapshot = feed.latest(AAPL, as_of)
    assert snapshot.sequence == 5  # the weekend print exists on the tape...
    verdict = assess(registry.get(AAPL), snapshot, as_of, FreshnessPolicy.defaults())
    assert verdict.fresh  # ...the data is fresh...
    assert not verdict.eligible  # ...but Saturday exposure is blocked
    assert not verdict.ready_for_exposure()
    assert any(r.startswith("market-closed:weekend") for r in verdict.reasons)


def test_stale_quote_rejected_by_age_and_flag():
    registry = default_registry()
    feed = _feed()
    # Crypto max age 30s; last ws print available 10:04:00, ask at 10:10.
    as_of = datetime(2026, 10, 31, 10, 10, 0, tzinfo=UTC)
    snapshot = feed.latest(BTC, as_of)
    assert snapshot.sequence == 5
    verdict = assess(registry.get(BTC), snapshot, as_of, FreshnessPolicy.defaults())
    assert not verdict.fresh
    assert verdict.age_seconds == 360
    assert any(r.startswith("data-older-than-max-age") for r in verdict.reasons)

    # A snapshot explicitly flagged stale is rejected regardless of age.
    flagged = snapshot.model_copy(update={"quality": ("stale",)})
    immediate = assess(
        registry.get(BTC), flagged, datetime(2026, 10, 31, 10, 4, 10, tzinfo=UTC)
    )
    assert not immediate.fresh
    assert "flagged-stale" in immediate.reasons


def test_no_data_and_unentitled_sources_fail_closed():
    registry = default_registry()
    feed = _feed()
    # BTC recording starts at 10:00:00; nothing available before it.
    early = feed.latest(BTC, datetime(2026, 10, 31, 9, 0, tzinfo=UTC))
    verdict = assess(registry.get(BTC), early, datetime(2026, 10, 31, 9, 0, tzinfo=UTC))
    assert not verdict.fresh and "no-data" in verdict.reasons

    # The unentitled coinbase-rest print (10:05:35) never becomes the decision quote.
    latest = feed.latest(BTC, datetime(2026, 10, 31, 10, 6, 0, tzinfo=UTC))
    assert latest.source == "coinbase-ws" and latest.sequence == 5
    unentitled = latest.model_copy(update={"entitled": False})
    denied = assess(registry.get(BTC), unentitled, datetime(2026, 10, 31, 10, 6, 0, tzinfo=UTC))
    assert not denied.fresh and "unentitled-source" in denied.reasons
