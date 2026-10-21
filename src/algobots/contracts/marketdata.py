"""Market-data and feature snapshot contracts (A05, roadmap §2).

Every :class:`MarketSnapshot` carries the three timestamps that make replay
honest: ``event_time`` (when it happened), ``available_time`` (when the source
published it — the point-in-time gate), and ``receive_time`` (when we saw it).
A later-published correction is a *new* record carrying ``correction_of``;
replaying an earlier as-of time never sees it (see
:mod:`algobots.marketdata.replay`).

:class:`FeatureSnapshot` is emitted by indicator computation that runs outside
execution callbacks (:mod:`algobots.marketdata.features`), only from completed
bars, with warmup/gap/stale status explicit — never silently.
"""

from __future__ import annotations

from typing import Annotated, ClassVar, Literal

from pydantic import Field, model_validator

from . import registry
from .base import DecimalStr, Identifier, Money, Quantity, UtcDatetime, VersionedContract

__all__ = [
    "FeatureSnapshot",
    "MarketSnapshot",
    "QualityFlag",
    "SnapshotStatus",
]

# Observation-quality flags. "ok" is the nominal flag; the rest are defects a
# freshness/eligibility check reacts to (algobots.marketdata.freshness).
QualityFlag = Literal["ok", "stale", "late", "corrected", "out-of-order", "incomplete"]

# Lifecycle of a feature computation.
SnapshotStatus = Literal["ready", "warmup", "stale", "gap"]


@registry.register
class MarketSnapshot(VersionedContract):
    """One recorded quote/trade observation, replayable as-of its timestamps.

    ``source`` is the price-source tag (e.g. ``coinbase-ws``); ``sequence`` is
    monotonic per (instrument, source). ``entitled`` records whether the
    recording account was entitled to this feed at event time — unentitled
    snapshots never satisfy a price request (source precedence applies only
    among entitled ones). At least one of bid/ask/last must be present.
    """

    contract_name: ClassVar[str] = "MarketSnapshot"
    contract_version: ClassVar[str] = "1.0"

    instrument_id: Identifier
    event_time: UtcDatetime
    available_time: UtcDatetime
    receive_time: UtcDatetime
    source: Identifier
    sequence: Annotated[int, Field(ge=1)]
    entitled: bool
    quality: tuple[QualityFlag, ...]
    bid: Money | None = None
    ask: Money | None = None
    bid_size: Quantity | None = None
    ask_size: Quantity | None = None
    last: Money | None = None
    last_size: Quantity | None = None
    correction_of: Annotated[int, Field(ge=1)] | None = None

    @model_validator(mode="after")
    def _time_order_and_content(self) -> MarketSnapshot:
        if self.available_time < self.event_time:
            raise ValueError("available_time precedes event_time (publication before the event)")
        if self.receive_time < self.available_time:
            raise ValueError("receive_time precedes available_time (saw it before it existed)")
        if self.bid is None and self.ask is None and self.last is None:
            raise ValueError("a snapshot carries at least one of bid/ask/last")
        if not self.quality:
            raise ValueError("quality flags are explicit; use ['ok'] for a nominal record")
        if len(set(self.quality)) != len(self.quality):
            raise ValueError("duplicate quality flags")
        for side, size in (("bid", self.bid_size), ("ask", self.ask_size), ("last", self.last_size)):
            if size is not None and getattr(self, side) is None:
                raise ValueError(f"{side}_size without {side}")
        return self


@registry.register
class FeatureSnapshot(VersionedContract):
    """One indicator evaluation over completed bars.

    ``status`` is ``ready`` only when warmup completed on an unbroken run of
    completed bars; ``warmup``/``gap``/``stale`` carry no values (a gap resets
    warmup, stale input is rejected before ingestion). Values are decimal
    strings so indicator outputs never round-trip through binary floats.
    """

    contract_name: ClassVar[str] = "FeatureSnapshot"
    contract_version: ClassVar[str] = "1.0"

    instrument_id: Identifier
    feature_set: Identifier
    bar_interval: Identifier
    bar_close_time: UtcDatetime
    computed_at: UtcDatetime
    status: SnapshotStatus
    warmup_bars_required: Annotated[int, Field(ge=1)]
    bars_consumed: Annotated[int, Field(ge=0)]
    gap_count: Annotated[int, Field(ge=0)]
    values: dict[str, DecimalStr] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _status_values_consistency(self) -> FeatureSnapshot:
        if self.status == "ready" and not self.values:
            raise ValueError("a ready feature snapshot carries values")
        if self.status != "ready" and self.values:
            raise ValueError(f"a {self.status} feature snapshot carries no values")
        if self.status == "gap" and self.gap_count < 1:
            raise ValueError("gap status requires at least one detected gap")
        return self
