"""A05 acceptance case 3 (bar half): completed-bar semantics, gap detection,
incomplete bars — plus feature warmup and stale-data rejection (item 3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from algobots.contracts.marketdata import MarketSnapshot
from algobots.instruments import default_registry
from algobots.marketdata import BarBuilder, FeatureFeed, IndicatorSpec, ReplayFeed, load_recording

BTC = "COINBASE:spot-crypto:BTC-USD"


def _snap(at: datetime, bid: str, ask: str, sequence: int, **extra) -> MarketSnapshot:
    return MarketSnapshot.model_validate(
        {
            "schema_version": "1.0",
            "instrument_id": BTC,
            "event_time": at.isoformat(),
            "available_time": at.isoformat(),
            "receive_time": at.isoformat(),
            "source": "coinbase-ws",
            "sequence": sequence,
            "entitled": True,
            "quality": ["ok"],
            "bid": {"amount": bid, "currency": "USD"},
            "ask": {"amount": ask, "currency": "USD"},
            **extra,
        }
    )


def _ws_stream() -> list[MarketSnapshot]:
    """The coinbase-ws minute prints of the fixture: 10:00 .. 10:04."""
    feed = ReplayFeed(load_recording())
    return [
        s
        for s in feed.recording.snapshots(BTC)
        if s.source == "coinbase-ws" and s.quality == ("ok",)
    ]


def test_bar_emits_only_when_a_later_interval_arrives():
    builder = BarBuilder(default_registry().get(BTC), 60)
    stream = _ws_stream()
    bars = [builder.on_snapshot(s) for s in stream]
    # Five ticks (10:00..10:04): four completions, the 10:04 bar still forming.
    assert [b.close_ts for b in bars if b] == [
        datetime(2026, 10, 31, 10, 1, tzinfo=UTC),
        datetime(2026, 10, 31, 10, 2, tzinfo=UTC),
        datetime(2026, 10, 31, 10, 3, tzinfo=UTC),
        datetime(2026, 10, 31, 10, 4, tzinfo=UTC),
    ]
    assert builder.current_incomplete is not None
    assert builder.current_incomplete.open_ts == datetime(2026, 10, 31, 10, 4, tzinfo=UTC)


def test_incomplete_bar_is_never_emitted():
    builder = BarBuilder(default_registry().get(BTC), 60)
    for s in _ws_stream():
        builder.on_snapshot(s)
    # The forming 10:04 bar has data but was never completed: nothing exposes it
    # as a completed bar (only current_incomplete, clearly named).
    assert builder.current_incomplete.ticks == 1
    assert builder.current_incomplete.close_ts == datetime(2026, 10, 31, 10, 5, tzinfo=UTC)


def test_gap_detection_counts_missing_intervals():
    builder = BarBuilder(default_registry().get(BTC), 60)
    ticks = [
        _snap(datetime(2026, 10, 31, 10, 0, tzinfo=UTC), "100", "100.1", 1),
        _snap(datetime(2026, 10, 31, 10, 1, tzinfo=UTC), "101", "101.1", 2),
        _snap(datetime(2026, 10, 31, 10, 5, tzinfo=UTC), "105", "105.1", 3),
        _snap(datetime(2026, 10, 31, 10, 6, tzinfo=UTC), "106", "106.1", 4),
    ]
    first = builder.on_snapshot(ticks[0])
    second = builder.on_snapshot(ticks[1])
    third = builder.on_snapshot(ticks[2])
    fourth = builder.on_snapshot(ticks[3])
    assert first is None
    assert second is not None and second.gap_before == 0
    # The 10:01 bar is intact; the hole (10:02-10:04) surfaces on the bar that
    # closes it: the 10:05 bar, emitted only when the 10:06 tick arrives.
    assert third is not None and third.gap_before == 0
    assert third.open_ts == datetime(2026, 10, 31, 10, 1, tzinfo=UTC)
    assert fourth is not None
    assert fourth.open_ts == datetime(2026, 10, 31, 10, 5, tzinfo=UTC)
    assert fourth.gap_before == 3  # 10:02-10:04 had no ticks
    assert builder.current_incomplete.open_ts == datetime(2026, 10, 31, 10, 6, tzinfo=UTC)


def test_feature_warmup_then_ready_with_explicit_values():
    instrument = default_registry().get(BTC)
    feed = FeatureFeed(instrument, 60, (IndicatorSpec("sma-close-3", "sma", 3),))
    statuses = []
    for s in _ws_stream():
        _, feature = feed.on_snapshot(s, s.available_time)
        if feature is not None:
            statuses.append(feature)
    # Bars 10:00/10:01/10:02 complete on ticks 2/3/4: warmup, warmup, ready.
    assert [f.status for f in statuses] == ["warmup", "warmup", "ready", "ready"]
    ready = statuses[2]
    assert ready.warmup_bars_required == 3 and ready.bars_consumed == 3
    mids = (Decimal("61000.15"), Decimal("61005.55"), Decimal("61010.05"))
    expected = sum(mids) / 3
    assert ready.values["sma-close-3"] == expected.quantize(Decimal("0.0000000001"))
    assert ready.bar_close_time == datetime(2026, 10, 31, 10, 3, tzinfo=UTC)


def test_gap_resets_feature_warmup():
    instrument = default_registry().get(BTC)
    feed = FeatureFeed(instrument, 60, (IndicatorSpec("sma-close-3", "sma", 3),))
    ticks = [
        _snap(datetime(2026, 10, 31, 10, 0, tzinfo=UTC), "100", "100.1", 1),
        _snap(datetime(2026, 10, 31, 10, 1, tzinfo=UTC), "101", "101.1", 2),
        _snap(datetime(2026, 10, 31, 10, 2, tzinfo=UTC), "102", "102.1", 3),
        _snap(datetime(2026, 10, 31, 10, 6, tzinfo=UTC), "106", "106.1", 4),
        _snap(datetime(2026, 10, 31, 10, 7, tzinfo=UTC), "107", "107.1", 5),
    ]
    results = [feed.on_snapshot(s, s.available_time) for s in ticks]
    features = [f for _, f in results if f is not None]
    # Bars 10:00/10:01/10:02 complete consecutively: warmup, warmup, ready.
    # The 10:06 tick lands after a 3-bucket hole, so the 10:06 bar (completed by
    # the 10:07 tick) reports gap_before == 3 and the engine resets warmup —
    # no value is ever emitted across the hole.
    assert [f.status for f in features] == ["warmup", "warmup", "ready", "gap"]
    gap_feature = features[3]
    assert gap_feature.gap_count == 3
    assert gap_feature.bars_consumed == 4
    assert not gap_feature.values
    assert feed.engine.warmup_bars_required == 3


def test_stale_input_is_rejected_before_touching_a_bar():
    instrument = default_registry().get(BTC)
    feed = FeatureFeed(instrument, 60, (IndicatorSpec("sma-close-3", "sma", 3),))
    tick = _ws_stream()[0]
    # Fresh at 10:00:10 (crypto max age 30s) — no bar yet, no feature.
    assert feed.on_snapshot(tick, tick.available_time + timedelta(seconds=10)) == (None, None)
    # Same input asked 10 minutes later is stale: an explicit stale feature, no bar.
    bar, feature = feed.on_snapshot(tick, tick.available_time + timedelta(minutes=10))
    assert bar is None
    assert feature is not None and feature.status == "stale" and not feature.values


def test_corrections_amend_quotes_not_bar_history():
    instrument = default_registry().get(BTC)
    feed = FeatureFeed(instrument, 60, (IndicatorSpec("sma-close-3", "sma", 3),))
    stream = _ws_stream()
    all_btc = ReplayFeed(load_recording()).recording.snapshots(BTC)
    correction = next(s for s in all_btc if s.correction_of is not None)
    assert correction.correction_of == 3  # the 10:30-published correction
    for s in stream:
        feed.on_snapshot(s, s.available_time)
    # Feeding the correction afterwards must not raise or rewrite closed bars:
    bar, feature = feed.on_snapshot(correction, correction.available_time)
    # Its event time (10:02) precedes barred history: skipped for bars, and the
    # point-in-time quote lives in replay, not here.
    assert feature is None or feature.status != "ready"


def test_event_time_must_be_ordered_for_bars():
    builder = BarBuilder(default_registry().get(BTC), 60)
    late = _snap(datetime(2026, 10, 31, 10, 5, tzinfo=UTC), "105", "105.1", 1)
    early = _snap(datetime(2026, 10, 31, 10, 0, tzinfo=UTC), "100", "100.1", 2)
    builder.on_snapshot(late)
    import pytest

    from algobots.marketdata import BarStreamError

    with pytest.raises(BarStreamError):
        builder.on_snapshot(early)
