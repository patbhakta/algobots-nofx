"""Eligibility and freshness assessment (A05 acceptance case 3).

Two orthogonal verdicts, both with explicit reasons:

- **eligible** — may this instrument take new exposure *now*: known metadata,
  entitled, market open per its calendar (weekend equities closed, 24/7 crypto
  open, DST handled by the calendar arithmetic).
- **fresh** — is the best available snapshot usable as input: present,
  entitled, within ``max_age`` of ``as_of`` measured on *available_time* (what
  we could know), and not flagged ``stale``.

Fail closed everywhere: unknown instrument, unentitled feed, no data, stale
quote, closed market — each blocks with a named reason (A05 recovery rule).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from algobots.contracts.instrument import Instrument
from algobots.contracts.marketdata import MarketSnapshot
from algobots.instruments.calendar import market_session

__all__ = ["FreshnessAssessment", "FreshnessPolicy", "assess"]

# Default max data age per product, in seconds (decision inputs older than
# this are stale regardless of the market being open).
DEFAULT_MAX_AGE_SECONDS: dict[str, int] = {
    "equity": 60,
    "etf": 60,
    "spot-crypto": 30,
    "perpetual-swap": 30,
}


@dataclass(frozen=True)
class FreshnessPolicy:
    max_age_seconds: dict[str, int]

    @classmethod
    def defaults(cls) -> FreshnessPolicy:
        return cls(dict(DEFAULT_MAX_AGE_SECONDS))

    def max_age_for(self, instrument: Instrument) -> int:
        return self.max_age_seconds.get(str(instrument.product), 0)


@dataclass(frozen=True)
class FreshnessAssessment:
    """``eligible`` = identity/entitlement/market-open permission to trade now.
    ``fresh`` = the snapshot is usable decision input. New exposure requires
    both (:meth:`ready_for_exposure`); each failure names its reason."""

    eligible: bool
    fresh: bool
    reasons: tuple[str, ...]
    age_seconds: int | None = None
    snapshot: MarketSnapshot | None = None

    def ready_for_exposure(self) -> bool:
        return self.eligible and self.fresh


def assess(
    instrument: Instrument,
    snapshot: MarketSnapshot | None,
    as_of: datetime,
    policy: FreshnessPolicy | None = None,
) -> FreshnessAssessment:
    """Assess one instrument at ``as_of`` against its best snapshot."""
    if as_of.utcoffset() is None:
        raise ValueError("as-of times must be offset-aware")
    policy = policy or FreshnessPolicy.defaults()
    now = as_of.astimezone(UTC)
    eligibility_reasons: list[str] = []

    session = market_session(instrument.calendar, instrument.timezone, now)
    if not session.open:
        eligibility_reasons.append(f"market-closed:{session.reason}")

    freshness_reasons: list[str] = []
    age: int | None = None
    if snapshot is None:
        freshness_reasons.append("no-data")
    elif not snapshot.entitled:
        freshness_reasons.append("unentitled-source")
    else:
        age = max(0, int((now - snapshot.available_time.astimezone(UTC)).total_seconds()))
        if age > policy.max_age_for(instrument):
            freshness_reasons.append(f"data-older-than-max-age:{age}s")
        if "stale" in snapshot.quality:
            freshness_reasons.append("flagged-stale")
        if snapshot.instrument_id != instrument.instrument_id:
            freshness_reasons.append("instrument-mismatch")

    return FreshnessAssessment(
        eligible=not eligibility_reasons,
        fresh=not freshness_reasons,
        reasons=tuple(eligibility_reasons + freshness_reasons),
        age_seconds=age,
        snapshot=snapshot,
    )
