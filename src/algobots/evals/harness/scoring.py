"""Scoring: per-band directional hit-rate with Wilson CIs, mean alpha, multiclass Brier.

Certification semantics (ported from the stock-vaults harness line, ALG-3086):
an edge is only demonstrated when the overall hit-rate Wilson lower bound
clears the majority-label baseline of the same scored set; per-band verdicts
use the same rule against the band's Wilson lower bound. Known-random
controls therefore provably never certify.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .records import DIRECTION_BANDS, DecisionRecord

DEFAULT_Z = 1.959963984540054


def wilson_interval(correct: int, total: int, z: float = DEFAULT_Z) -> tuple[float, float] | None:
    """Wilson score interval for a binomial proportion; None when total is 0."""
    if total <= 0:
        return None
    p = correct / total
    z2 = z * z
    denom = 1.0 + z2 / total
    centre = (p + z2 / (2.0 * total)) / denom
    half = z * math.sqrt(p * (1.0 - p) / total + z2 / (4.0 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def realized_band(record: DecisionRecord, flat_threshold: float) -> str | None:
    """Classify a settled record's effective realized return into a band.

    The threshold is explicit and travels with the report: `up` is a return
    strictly above +flat_threshold, `down` strictly below -flat_threshold,
    `flat` inside the inclusive band. Returns None for unsettled records.
    """
    if not record.settled:
        return None
    realized = record.effective_realized_return
    if realized is None:
        return None
    upper = record.bands[0]
    middle = record.bands[1]
    lower = record.bands[2]
    if realized > flat_threshold:
        return upper
    if realized < -flat_threshold:
        return lower
    return middle


@dataclass
class BandScore:
    band: str
    count: int = 0
    correct: int = 0
    alpha_sum: float = 0.0
    alpha_n: int = 0
    brier_sum: float = 0.0
    ci_low: float | None = None
    ci_high: float | None = None
    beats_baseline: bool | None = None

    @property
    def hit_rate(self) -> float | None:
        return self.correct / self.count if self.count else None

    @property
    def mean_alpha(self) -> float | None:
        return self.alpha_sum / self.alpha_n if self.alpha_n else None

    @property
    def mean_brier(self) -> float | None:
        return self.brier_sum / self.count if self.count else None

    def to_dict(self) -> dict:
        return {
            "band": self.band,
            "count": self.count,
            "correct": self.correct,
            "hit_rate": self.hit_rate,
            "hit_rate_wilson_95": [self.ci_low, self.ci_high] if self.ci_low is not None else None,
            "mean_alpha": self.mean_alpha,
            "mean_brier": self.mean_brier,
            "beats_baseline": self.beats_baseline,
        }


def _case_brier(record: DecisionRecord, flat_threshold: float = 0.003) -> float:
    """Sum over bands of (p - o)^2, o = 1 for the REALIZED band (not the predicted one)."""
    realized = realized_band(record, flat_threshold)
    total = 0.0
    for band in record.bands:
        p = record.probabilities.get(band, 0.0)
        observed = 1.0 if realized == band else 0.0
        total += (p - observed) ** 2
    return total


def multiclass_brier(
    records: Iterable[DecisionRecord], flat_threshold: float = 0.003
) -> float | None:
    """Mean multiclass Brier score over settled records against their realized band."""
    scored = [(r, _case_brier(r, flat_threshold)) for r in records if r.settled]
    if not scored:
        return None
    return sum(b for _, b in scored) / len(scored)


def _score_subset(
    records: Sequence[DecisionRecord], band: str | None, flat_threshold: float, label: str
) -> BandScore:
    score = BandScore(band=label)
    for record in records:
        if band is not None and record.band != band:
            continue
        outcome = realized_band(record, flat_threshold)
        if outcome is None:
            continue
        score.count += 1
        score.brier_sum += _case_brier(record, flat_threshold)
        if outcome == record.band:
            score.correct += 1
        alpha = record.alpha
        if alpha is not None and math.isfinite(alpha):
            score.alpha_sum += alpha
            score.alpha_n += 1
    interval = wilson_interval(score.correct, score.count)
    if interval is not None:
        score.ci_low, score.ci_high = interval
    return score


@dataclass
class HarnessSummary:
    flat_threshold: float
    per_band: dict[str, BandScore]
    overall: BandScore
    brier: float | None
    unsettled: int
    bands: tuple[str, ...]
    base_rates: dict[str, float] = field(default_factory=dict)
    baseline_hit_rate: float | None = None
    edge_demonstrated: bool | None = None

    def to_dict(self) -> dict:
        return {
            "flat_threshold": self.flat_threshold,
            "bands": list(self.bands),
            "per_band": {k: v.to_dict() for k, v in self.per_band.items()},
            "overall": self.overall.to_dict(),
            "brier": self.brier,
            "unsettled": self.unsettled,
            "base_rates": dict(self.base_rates),
            "baseline_hit_rate": self.baseline_hit_rate,
            "edge_demonstrated": self.edge_demonstrated,
        }


def _majority_label_baseline(
    settled: Sequence[DecisionRecord], flat_threshold: float
) -> tuple[dict[str, float], float | None]:
    """Majority-label baseline over realized labels of the scored set itself.

    The baseline predicts the most frequent realized label everywhere; its
    hit-rate is that label's base rate. Returned as (base_rates, hit_rate).
    """
    label_counts: dict[str, int] = {}
    for record in settled:
        outcome = realized_band(record, flat_threshold)
        if outcome is not None:
            label_counts[outcome] = label_counts.get(outcome, 0) + 1
    total = sum(label_counts.values())
    if not total:
        return {}, None
    base_rates = {label: count / total for label, count in sorted(label_counts.items())}
    return base_rates, max(base_rates.values())


def summarize(
    records: Sequence[DecisionRecord],
    flat_threshold: float = 0.003,
    bands: tuple[str, ...] | None = None,
) -> HarnessSummary:
    """Score settled records per predicted band plus overall.

    Unsettled records are counted and excluded from every rate — an unfinished
    horizon is never a win or a loss. Every non-empty band and the overall
    score carry a `beats_baseline` verdict against the majority-label
    baseline; `edge_demonstrated` is True only when the overall Wilson lower
    bound clears that baseline, so known-random controls never certify.
    """
    active_bands = tuple(bands) if bands else DIRECTION_BANDS
    settled = [r for r in records if r.settled and realized_band(r, flat_threshold) is not None]
    unsettled = len(records) - len(settled)
    per_band = {band: _score_subset(settled, band, flat_threshold, band) for band in active_bands}
    overall = _score_subset(settled, None, flat_threshold, "overall")
    brier = multiclass_brier(settled, flat_threshold)
    base_rates, baseline_hit_rate = _majority_label_baseline(settled, flat_threshold)
    edge_demonstrated: bool | None = None
    if baseline_hit_rate is not None:
        for score in [*per_band.values(), overall]:
            if score.count:
                score.beats_baseline = score.ci_low is not None and score.ci_low > baseline_hit_rate
        edge_demonstrated = overall.ci_low is not None and overall.ci_low > baseline_hit_rate
    return HarnessSummary(
        flat_threshold=flat_threshold,
        per_band=per_band,
        overall=overall,
        brier=brier,
        unsettled=unsettled,
        bands=active_bands,
        base_rates=base_rates,
        baseline_hit_rate=baseline_hit_rate,
        edge_demonstrated=edge_demonstrated,
    )
