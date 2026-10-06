"""Mandatory baselines: a decision model only counts when it beats chance honestly."""

from __future__ import annotations

import random
from collections.abc import Sequence

from .records import DIRECTION_BANDS, DecisionRecord
from .scoring import HarnessSummary, realized_band, summarize


def chance_level(bands: tuple[str, ...]) -> float:
    return 1.0 / len(bands)


class RandomBaseline:
    """Seeded uniform predictor; the known-random reference, reproduced at <= chance."""

    def __init__(self, seed: int = 0, bands: tuple[str, ...] = DIRECTION_BANDS) -> None:
        self.seed = seed
        self.bands = bands
        self._rng = random.Random(seed)

    def predict(self, ticker: str, trade_date: str) -> tuple[str, dict[str, float]]:
        del ticker, trade_date
        weight = 1.0 / len(self.bands)
        probs = {band: weight for band in self.bands}
        return self._rng.choice(self.bands), probs


class AlwaysFlatBaseline:
    """Predicts the middle band with full mass; the do-nothing reference."""

    def __init__(self, bands: tuple[str, ...] = DIRECTION_BANDS) -> None:
        self.bands = bands

    def predict(self, ticker: str, trade_date: str) -> tuple[str, dict[str, float]]:
        del ticker, trade_date
        probs = {band: 0.0 for band in self.bands}
        probs[self.bands[1]] = 1.0
        return self.bands[1], probs


def persistence_baseline(
    records: Sequence[DecisionRecord], flat_threshold: float = 0.003
) -> dict[tuple[str, str], tuple[str, dict[str, float]]]:
    """Predict each (ticker, trade_date) band as that ticker's previous settled realized band.

    Realized bands use the same explicit flat_threshold as the model summary, so the
    comparison is apples-to-apples.
    """
    last: dict[str, tuple[str, str]] = {}
    predictions: dict[tuple[str, str], tuple[str, dict[str, float]]] = {}
    for record in sorted(records, key=lambda r: (r.ticker, r.trade_date)):
        if record.ticker in last and last[record.ticker][0] != record.trade_date:
            band = last[record.ticker][1]
            probs = {b: 0.0 for b in record.bands}
            probs[band] = 1.0
            predictions[(record.ticker, record.trade_date)] = (band, probs)
        realized = realized_band(record, flat_threshold) if record.settled else None
        if realized is not None:
            last[record.ticker] = (record.trade_date, realized)
    return predictions


def baseline_summaries(
    baseline_records_by_name: dict[str, list[DecisionRecord]],
    flat_threshold: float = 0.003,
) -> dict[str, HarnessSummary]:
    """Summarize each baseline's records with the identical protocol as the model's."""
    return {
        name: summarize(baseline_records, flat_threshold=flat_threshold)
        for name, baseline_records in baseline_records_by_name.items()
    }


def random_at_or_below_chance(summary: HarnessSummary, tolerance: float = 0.0) -> bool:
    """Acceptance helper: the random baseline's overall hit-rate must sit at or below chance.

    The Wilson interval is reported alongside so reviewers can see whether the
    point estimate is statistically distinguishable from chance.
    """
    chance = chance_level(summary.bands)
    overall = summary.overall
    if overall.hit_rate is None:
        return False
    return overall.hit_rate <= chance + tolerance
