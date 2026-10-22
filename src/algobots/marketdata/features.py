"""Indicator feature computation outside execution callbacks (A05 item 3).

:class:`FeatureEngine` consumes **completed bars only** (never the forming
bar), tracks warmup explicitly, resets warmup when a gap is detected on its
input, and reports stale input instead of silently aging values. Feature
values are decimal strings quantized to 10 places — no binary floats on the
feature path. :class:`FeatureFeed` composes freshness -> bars -> engine so
stale snapshots are rejected before they can touch a bar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Literal

from algobots.contracts.instrument import Instrument
from algobots.contracts.marketdata import FeatureSnapshot, MarketSnapshot
from algobots.marketdata.bars import Bar, BarBuilder
from algobots.marketdata.freshness import FreshnessPolicy, assess

__all__ = ["FeatureEngine", "FeatureFeed", "IndicatorSpec", "QUANTUM"]

# Feature values are decimal strings at a fixed precision.
QUANTUM = Decimal("0.0000000001")
FeatureKind = Literal["sma", "ema"]


@dataclass(frozen=True)
class IndicatorSpec:
    name: str  # e.g. "sma-close-3"
    kind: FeatureKind
    period: int

    def __post_init__(self) -> None:
        if self.period < 1:
            raise ValueError("indicator period must be >= 1")


def _q(value: Decimal) -> Decimal:
    return value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


class FeatureEngine:
    """Deterministic indicator evaluation over completed bars."""

    def __init__(
        self, instrument_id: str, bar_interval: str, specs: tuple[IndicatorSpec, ...]
    ) -> None:
        if not specs:
            raise ValueError("a feature engine needs at least one indicator spec")
        self._instrument_id = instrument_id
        self._bar_interval = bar_interval
        self._specs = specs
        self._warmup = max(s.period for s in specs)
        self._closes: list[Decimal] = []
        self._bars_consumed = 0
        self._gap_count = 0
        self._last_close_time: datetime | None = None
        self._ema_state: dict[str, Decimal] = {}

    @property
    def warmup_bars_required(self) -> int:
        return self._warmup

    def _feature_set(self) -> str:
        return "+".join(sorted(s.name for s in self._specs))

    def _snapshot(
        self,
        bar_close_time: datetime,
        computed_at: datetime,
        status: str,
        values: dict[str, Decimal],
        gap_count: int,
    ) -> FeatureSnapshot:
        return FeatureSnapshot(
            schema_version="1.0",
            instrument_id=self._instrument_id,
            feature_set=self._feature_set(),
            bar_interval=self._bar_interval,
            bar_close_time=bar_close_time.astimezone(UTC),
            computed_at=computed_at.astimezone(UTC),
            status=status,
            warmup_bars_required=self._warmup,
            bars_consumed=self._bars_consumed,
            gap_count=gap_count,
            values={k: _q(v) for k, v in values.items()},
        )

    def on_bar(self, bar: Bar, now: datetime) -> FeatureSnapshot:
        """Consume one completed bar; a gap resets warmup before this bar."""
        gap = bar.gap_before
        if gap:
            self._closes.clear()
            self._ema_state.clear()
            self._gap_count += gap
            self._bars_consumed += 1
            self._last_close_time = bar.close_ts
            return self._snapshot(bar.close_ts, now, "gap", {}, gap)
        self._closes.append(bar.close)
        self._bars_consumed += 1
        self._last_close_time = bar.close_ts
        if len(self._closes) < self._warmup:
            return self._snapshot(bar.close_ts, now, "warmup", {}, 0)
        values: dict[str, Decimal] = {}
        for spec in self._specs:
            window = self._closes[-spec.period :]
            if spec.kind == "sma":
                values[spec.name] = sum(window) / Decimal(len(window))
            else:  # ema, seeded with the SMA at the warmup boundary
                if spec.name not in self._ema_state:
                    self._ema_state[spec.name] = sum(window) / Decimal(len(window))
                else:
                    alpha = Decimal(2) / (Decimal(spec.period) + 1)
                    prev = self._ema_state[spec.name]
                    self._ema_state[spec.name] = alpha * bar.close + (1 - alpha) * prev
                values[spec.name] = self._ema_state[spec.name]
        return self._snapshot(bar.close_ts, now, "ready", values, 0)

    def mark_stale(self, now: datetime) -> FeatureSnapshot:
        """Stale input was rejected; report status without inventing values."""
        close_time = self._last_close_time or now
        return self._snapshot(close_time, now, "stale", {}, 0)


class FeatureFeed:
    """Freshness-gated snapshot -> completed bars -> features pipeline."""

    def __init__(
        self,
        instrument: Instrument,
        interval_seconds: int,
        specs: tuple[IndicatorSpec, ...],
        policy: FreshnessPolicy | None = None,
    ) -> None:
        self._instrument = instrument
        self._builder = BarBuilder(instrument, interval_seconds)
        self._engine = FeatureEngine(instrument.instrument_id, f"{interval_seconds}s", specs)
        self._policy = policy or FreshnessPolicy.defaults()

    @property
    def engine(self) -> FeatureEngine:
        return self._engine

    def on_snapshot(
        self, snap: MarketSnapshot, as_of: datetime
    ) -> tuple[Bar | None, FeatureSnapshot | None]:
        """Stale/unentitled input is rejected; otherwise feed bars to the engine.

        A snapshot whose *event* time precedes the events already barred is a
        correction/replay of an earlier print: it amends point-in-time quotes
        (replay) but never rewrites bar history — it is skipped here.
        """
        assessment = assess(self._instrument, snap, as_of, self._policy)
        if not assessment.fresh:
            return None, self._engine.mark_stale(as_of)
        last = self._builder.last_event_time
        if last is not None and snap.event_time.astimezone(UTC) < last:
            return None, None
        bar = self._builder.on_snapshot(snap)
        if bar is None:
            return None, None
        return bar, self._engine.on_bar(bar, as_of)
