"""A05 acceptance case 4: replaying an earlier as-of time hides later-published
records — corrections (and, by the same available_time gate, later-published
filings) never leak backwards into a decision."""

from __future__ import annotations

from datetime import UTC, datetime

from algobots.marketdata import ReplayFeed, load_recording
from algobots.marketdata.precedence import (
    DEFAULT_RANKING,
    PriceSourcePrecedence,
    UnknownSourceError,
)

AAPL = "XNAS:equity:AAPL"
BTC = "COINBASE:spot-crypto:BTC-USD"


def _feed() -> ReplayFeed:
    return ReplayFeed(load_recording())


def test_correction_unavailable_before_publication():
    # coinbase-ws seq 6 corrects the 10:02 print but is published at 10:30.
    feed = _feed()
    before = feed.latest(BTC, datetime(2026, 10, 31, 10, 29, 0, tzinfo=UTC))
    assert before.sequence == 5
    assert str(before.bid.amount) == "61015.00"

    # One second past publication the correction is the decision quote.
    after = feed.latest(BTC, datetime(2026, 10, 31, 10, 30, 0, tzinfo=UTC))
    assert after.sequence == 6
    assert after.correction_of == 3
    assert str(after.bid.amount) == "61011.00"


def test_later_event_time_never_outruns_its_available_time():
    # The AAPL correction carries an EARLIER event time (13:45) but a later
    # available time (15:30): replay at 15:00 must still see the 14:05 print.
    feed = _feed()
    verdict = feed.latest(AAPL, datetime(2026, 10, 30, 15, 0, tzinfo=UTC))
    assert verdict.sequence == 4
    corrected = feed.latest(AAPL, datetime(2026, 10, 30, 16, 0, tzinfo=UTC))
    assert corrected.sequence == 6 and corrected.correction_of == 2


def test_as_of_view_is_stable_under_replay():
    feed = _feed()
    for as_of, seq in (
        (datetime(2026, 10, 31, 10, 0, 30, tzinfo=UTC), 1),
        (datetime(2026, 10, 31, 10, 2, 0, tzinfo=UTC), 3),
        (datetime(2026, 10, 31, 10, 3, 0, tzinfo=UTC), 4),
    ):
        assert feed.latest(BTC, as_of).sequence == seq


def test_price_source_precedence_picks_entitled_websocket_over_rest():
    feed = _feed()
    # 10:00:06: ws seq 1 (avail 10:00:00) vs rest seq 1 (avail 10:00:05) — both
    # entitled; rank decides, not recency.
    chosen = feed.latest(BTC, datetime(2026, 10, 31, 10, 0, 6, tzinfo=UTC))
    assert chosen.source == "coinbase-ws" and chosen.sequence == 1

    # 10:06:00: rest seq 2 is newer but unentitled — ws seq 5 stays the answer.
    later = feed.latest(BTC, datetime(2026, 10, 31, 10, 6, 0, tzinfo=UTC))
    assert later.source == "coinbase-ws" and later.sequence == 5


def test_precedence_fails_closed_on_unknown_sources():
    precedence = PriceSourcePrecedence(DEFAULT_RANKING)
    import pytest

    with pytest.raises(UnknownSourceError):
        precedence.rank("COINBASE", "coinbase-pro")
    # And an unranked source never wins selection even when it is the only one.

    recording = load_recording()
    ws = [s for s in recording.snapshots(BTC) if s.source == "coinbase-ws"][0]
    rogue = ws.model_copy(update={"source": "coinbase-pro", "sequence": 99})
    selected = precedence.select("COINBASE", {"coinbase-pro": rogue})
    assert selected is None


def test_raw_records_retained_for_correction_replay():
    recording = load_recording()
    assert len(recording.raw) == len(recording.snapshots_all)
    # Every raw line still parses to its contract object (recovery path).
    import json

    from algobots.contracts.marketdata import MarketSnapshot

    for line, snap in zip(recording.raw, recording.snapshots_all, strict=False):
        parsed = MarketSnapshot.model_validate(json.loads(line))
        if (parsed.source, parsed.sequence) == (snap.source, snap.sequence):
            assert parsed == snap
