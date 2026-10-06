"""Decision and settlement record schema for the harness."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

DIRECTION_BANDS: tuple[str, ...] = ("up", "flat", "down")


class MoneyGateError(Exception):
    """A run that gates money contains decisions without preregistration."""


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _check_iso_date(value: str, name: str) -> None:
    try:
        date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO YYYY-MM-DD date, got {value!r}") from exc


@dataclass(frozen=True)
class SettlementCorrection:
    """Append-only correction to a settled outcome; never overwrites the original."""

    corrected_at: str
    realized_return: float
    benchmark_return: float | None
    reason: str


@dataclass
class DecisionRecord:
    """One prospective decision, later settled against realized outcome.

    The record is created before the outcome exists. Settlement fields stay
    unset until the horizon closes. Probabilities are the model's own
    distribution over `bands`; they are never treated as calibrated win rates.
    """

    decision_id: str
    ticker: str
    trade_date: str
    band: str
    probabilities: dict[str, float]
    horizon_days: int
    bands: tuple[str, ...] = DIRECTION_BANDS
    confidence: float | None = None
    model_name: str = "unknown"
    model_revision: str = "unpinned"
    question_set_revision: str = "unpinned"
    benchmark_ticker: str | None = None
    preregistered_at: str | None = None
    created_at: str = field(default_factory=_utc_now_iso)
    settled: bool = False
    realized_return: float | None = None
    benchmark_return: float | None = None
    settled_at: str | None = None
    settlement_notes: str | None = None
    corrections: tuple[SettlementCorrection, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _check_iso_date(self.trade_date, "trade_date")
        if self.band not in self.bands:
            raise ValueError(f"band {self.band!r} not in bands {self.bands}")
        if not isinstance(self.probabilities, dict):
            raise ValueError("probabilities must be a mapping of band -> float")
        for key, value in self.probabilities.items():
            if key not in self.bands:
                raise ValueError(f"probability key {key!r} not in bands {self.bands}")
            if not math.isfinite(value) or value < 0.0 or value > 1.0:
                raise ValueError(f"probability for {key!r} must be finite in [0, 1], got {value}")
        if self.confidence is not None and (
            not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0
        ):
            raise ValueError("confidence must be finite in [0, 1] when provided")
        if self.horizon_days < 1:
            raise ValueError("horizon_days must be >= 1")
        if self.settled:
            raise ValueError("construct decisions unsettled; settle via settle()")
        for name in ("realized_return", "benchmark_return", "settled_at"):
            if getattr(self, name) is not None:
                raise ValueError(f"{name} cannot be set before settlement")

    @property
    def alpha(self) -> float | None:
        if self.realized_return is None:
            return None
        if self.benchmark_return is None:
            return None
        return self.realized_return - self.benchmark_return

    def settle(
        self,
        realized_return: float,
        benchmark_return: float | None = None,
        settled_at: str | None = None,
        notes: str | None = None,
    ) -> None:
        if not math.isfinite(realized_return):
            raise ValueError("realized_return must be finite")
        if self.settled:
            raise ValueError(
                f"decision {self.decision_id} already settled at {self.settled_at}; "
                "append a SettlementCorrection instead of overwriting"
            )
        self.settled = True
        self.realized_return = realized_return
        self.benchmark_return = benchmark_return
        self.settled_at = settled_at or _utc_now_iso()
        self.settlement_notes = notes

    def correct(
        self,
        realized_return: float,
        benchmark_return: float | None = None,
        reason: str = "",
        corrected_at: str | None = None,
    ) -> None:
        if not self.settled:
            raise ValueError("correct() applies to settled decisions only")
        self.corrections = self.corrections + (
            SettlementCorrection(
                corrected_at=corrected_at or _utc_now_iso(),
                realized_return=realized_return,
                benchmark_return=benchmark_return,
                reason=reason,
            ),
        )

    @property
    def effective_realized_return(self) -> float | None:
        if self.corrections:
            return self.corrections[-1].realized_return
        return self.realized_return

    @property
    def effective_benchmark_return(self) -> float | None:
        if self.corrections and self.corrections[-1].benchmark_return is not None:
            return self.corrections[-1].benchmark_return
        return self.benchmark_return

    def to_dict(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "ticker": self.ticker,
            "trade_date": self.trade_date,
            "band": self.band,
            "probabilities": dict(self.probabilities),
            "horizon_days": self.horizon_days,
            "bands": list(self.bands),
            "confidence": self.confidence,
            "model_name": self.model_name,
            "model_revision": self.model_revision,
            "question_set_revision": self.question_set_revision,
            "benchmark_ticker": self.benchmark_ticker,
            "preregistered_at": self.preregistered_at,
            "created_at": self.created_at,
            "settled": self.settled,
            "realized_return": self.realized_return,
            "benchmark_return": self.benchmark_return,
            "settled_at": self.settled_at,
            "settlement_notes": self.settlement_notes,
            "corrections": [vars(c) | {} for c in self.corrections],
        }
