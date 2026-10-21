"""Recorded market data, replay, freshness, bars, features and status (A05).

Seam notes (do not rebuild; integrate): A06's ``engine/workers/fixture.py``
synthetic quote stream stays as-is (it models no event-time/available-time
semantics — these recordings supersede the shape, not the file), and
``engine/sleeve.py`` Kalshi identities are an excluded asset class whose
distinct-ID discipline this registry shares but does not host.
"""

from algobots.marketdata.bars import Bar, BarBuilder, BarStreamError
from algobots.marketdata.features import FeatureEngine, FeatureFeed, IndicatorSpec
from algobots.marketdata.freshness import (
    FreshnessAssessment,
    FreshnessPolicy,
    assess,
)
from algobots.marketdata.fx import FxRateBook, FxUnavailableError, load_fx_book
from algobots.marketdata.precedence import PriceSourcePrecedence, UnknownSourceError
from algobots.marketdata.recorded import Recording, RecordingError, load_recording, recordings_path
from algobots.marketdata.replay import ReplayFeed
from algobots.marketdata.status import InstrumentStatus, watchlist_status

__all__ = [
    "Bar",
    "BarBuilder",
    "BarStreamError",
    "FeatureEngine",
    "FeatureFeed",
    "FreshnessAssessment",
    "FreshnessPolicy",
    "FxRateBook",
    "FxUnavailableError",
    "IndicatorSpec",
    "InstrumentStatus",
    "PriceSourcePrecedence",
    "Recording",
    "RecordingError",
    "ReplayFeed",
    "UnknownSourceError",
    "assess",
    "load_fx_book",
    "load_recording",
    "recordings_path",
    "watchlist_status",
]
