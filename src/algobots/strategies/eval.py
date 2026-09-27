"""Pure evaluation of strategy DSL conditions over indicator windows (S4.2).

No I/O, no clocks, no DB: `evaluate(spec, bars)` maps a validated spec and a
bar window to entry/exit booleans. Indicator math is deterministic and
hand-checkable:

- SMA(n): mean of the trailing n values.
- EMA(n): seeded with SMA(first n), then `k = 2 / (n + 1)` recursion.
- RSI(n): Wilder smoothing over gains/losses; `avg_loss == 0` → 100.

Series are computed over the full window and None-padded before they are
defined, so cross operators can read the previous value explicitly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from algobots.strategies.dsl import (
    Condition,
    ConditionGroup,
    ConditionLeaf,
    SeriesRef,
    StrategySpec,
    ValueOperand,
    min_warmup,
)

__all__ = ["Bar", "Evaluation", "InsufficientWarmup", "bars_from_closes", "evaluate"]


@dataclass(frozen=True, slots=True)
class Bar:
    """One OHLCV bar. `volume` is optional (defaults keep close-only tests terse)."""

    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


def bars_from_closes(closes: Sequence[float]) -> list[Bar]:
    """Convenience: synththesize bars whose every source equals `close`."""
    return [Bar(open=c, high=c, low=c, close=c) for c in closes]


class InsufficientWarmup(ValueError):
    """The window is shorter than the spec's warmup requirement."""


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Booleans evaluated on the final bar of the window."""

    entry: bool
    exit: bool


def evaluate(spec: StrategySpec, bars: Sequence[Bar]) -> Evaluation:
    """Evaluate entry/exit conditions on the last bar (pure)."""
    needed = min_warmup(spec)
    if len(bars) < needed:
        raise InsufficientWarmup(f"need {needed} bars, got {len(bars)}")
    return Evaluation(
        entry=_eval_condition(spec.entry, bars),
        exit=_eval_condition(spec.exit, bars),
    )


# --- condition tree -----------------------------------------------------------


def _eval_condition(condition: Condition, bars: Sequence[Bar]) -> bool:
    if isinstance(condition, ConditionGroup):
        children = condition.all or condition.any or []
        if condition.all is not None:
            return all(_eval_condition(child, bars) for child in children)
        return any(_eval_condition(child, bars) for child in children)
    return _eval_leaf(condition, bars)


def _eval_leaf(leaf: ConditionLeaf, bars: Sequence[Bar]) -> bool:
    left = _series(leaf.left, bars)
    if isinstance(leaf.right, ValueOperand):
        right = [leaf.right.value] * len(bars)
    else:
        right = _series(leaf.right, bars)

    # The last defined point of each series is the comparison point; a cross
    # additionally reads the point before it.
    lv, ln = _last_defined(left)
    rv, rn = _last_defined(right)

    if leaf.op == "gt":
        return lv > rv
    if leaf.op == "gte":
        return lv >= rv
    if leaf.op == "lt":
        return lv < rv
    if leaf.op == "lte":
        return lv <= rv
    if leaf.op == "eq":
        return lv == rv

    lp = _before(left, ln)
    rp = _before(right, rn)
    if leaf.op == "crosses_above":
        return lp <= rp and lv > rv
    return lp >= rp and lv < rv  # crosses_below


def _last_defined(series: list[float | None]) -> tuple[float, int]:
    """The most recent defined value and its index."""
    for index in range(len(series) - 1, -1, -1):
        value = series[index]
        if value is not None:
            return value, index
    raise AssertionError("series has no defined values (warmup guard should have caught this)")


def _before(series: list[float | None], index: int) -> float:
    """The defined value immediately before `index` (cross operand)."""
    for cursor in range(index - 1, -1, -1):
        value = series[cursor]
        if value is not None:
            return value
    raise AssertionError("no previous value (warmup guard should have caught this)")


# --- indicator math ------------------------------------------------------------


def _series(ref: SeriesRef, bars: Sequence[Bar]) -> list[float | None]:
    raw = [float(getattr(bar, ref.source)) for bar in bars]
    if ref.indicator is None:
        return raw
    period = ref.params.period if ref.params else 2
    if ref.indicator == "sma":
        return _sma(raw, period)
    if ref.indicator == "ema":
        return _ema(raw, period)
    return _rsi(raw, period)


def _sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    window = 0.0
    for index, value in enumerate(values):
        window += value
        if index >= period:
            window -= values[index - period]
        if index >= period - 1:
            out[index] = window / period
    return out


def _ema(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    k = 2.0 / (period + 1)
    current = seed
    for index in range(period, len(values)):
        current = values[index] * k + current * (1.0 - k)
        out[index] = current
    return out


def _rsi(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    if len(values) < period + 1:
        return out
    deltas = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [d if d > 0 else 0.0 for d in deltas]
    losses = [-d if d < 0 else 0.0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    out[period] = _rsi_value(avg_gain, avg_loss)
    for index in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[index]) / period
        avg_loss = (avg_loss * (period - 1) + losses[index]) / period
        out[index + 1] = _rsi_value(avg_gain, avg_loss)
    return out


def _rsi_value(avg_gain: float, avg_loss: float) -> float:
    if avg_loss == 0.0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
