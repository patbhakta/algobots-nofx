"""Point-in-time replay over recorded snapshots (A05 acceptance case 4).

Replay gates on **available_time**: a snapshot is visible to an as-of decision
only if the source had published it by then. Later-published corrections (and,
by the same mechanism, later-published filings/metadata) are invisible to an
earlier decision no matter how early their *event* time claims to be.
Corrections win naturally: they carry a later sequence and a later
available_time than the record they correct.
"""

from __future__ import annotations

from datetime import UTC, datetime

from algobots.contracts.marketdata import MarketSnapshot
from algobots.marketdata.precedence import DEFAULT_RANKING, PriceSourcePrecedence
from algobots.marketdata.recorded import Recording

__all__ = ["ReplayFeed"]


def _as_utc(value: datetime) -> datetime:
    if value.utcoffset() is None:
        raise ValueError("as-of times must be offset-aware")
    return value.astimezone(UTC)


class ReplayFeed:
    """As-of queries over one :class:`Recording`, with source precedence."""

    def __init__(
        self,
        recording: Recording,
        precedence: PriceSourcePrecedence | None = None,
    ) -> None:
        self._recording = recording
        self._precedence = precedence or PriceSourcePrecedence(DEFAULT_RANKING)

    @property
    def recording(self) -> Recording:
        return self._recording

    def latest_available(self) -> datetime | None:
        """The newest ``available_time`` across the recording (a deterministic
        default as-of for read-only surfaces)."""
        snapshots = self._recording.snapshots_all
        if not snapshots:
            return None
        return max(s.available_time for s in snapshots)

    def snapshots(
        self, instrument_id: str, as_of: datetime | None = None
    ) -> tuple[MarketSnapshot, ...]:
        """Snapshots of one instrument published by ``as_of`` (latest when ``None``),
        across all sources, ordered by (available_time, sequence)."""
        if as_of is None:
            return self._recording.snapshots(instrument_id)
        cutoff = _as_utc(as_of)
        return tuple(
            s
            for s in self._recording.snapshots(instrument_id)
            if s.available_time <= cutoff
        )

    def latest(
        self,
        instrument_id: str,
        as_of: datetime | None = None,
        venue: str | None = None,
    ) -> MarketSnapshot | None:
        """The decision-grade snapshot: best-precedence entitled source's newest
        published record at ``as_of``. Unentitled or unranked sources never win."""
        available = self.snapshots(instrument_id, as_of)
        if not available:
            return None
        if venue is None:
            # Derive from the executable ID's frozen triple (venue is its first part).
            venue = instrument_id.split(":", 1)[0]
        per_source: dict[str, MarketSnapshot] = {}
        for snap in available:
            per_source[snap.source] = snap  # ordered by (available, sequence): last = newest
        selected = self._precedence.select(venue, per_source)
        return None if selected is None else selected[1]
