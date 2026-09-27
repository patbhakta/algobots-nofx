"""Pure evaluation tests vs hand-computed indicator values (AC 1).

Every expected value below is hand-computed arithmetic, not library output.

SMA/EMA fixtures use closes [10, 11, 12, 13, 14]:
- sma3 = [None, None, 11, 12, 13]
- ema3: seed at idx2 = sma3(first 3) = 11; k = 2/(3+1) = 0.5
        idx3 = 13*0.5 + 11*0.5 = 12; idx4 = 14*0.5 + 12*0.5 = 13

Crossover fixture uses closes [10, 11, 12, 13, 8, 9, 11]:
- sma2 = [None, 10.5, 11.5, 12.5, 10.5, 8.5, 10]
- sma3 = [None, None, 11, 12, 11, 10, 28/3]
- last bar: sma2=10 > sma3=28/3; prev bar: sma2=8.5 <= sma3=10 → crosses_above
- sma4 = [None, None, None, 11.5, 11.0, 10.5, 10.25] → does NOT cross sma3
  (prev: sma4=10.5 > sma3=10)

RSI(3) fixture uses closes [10, 11, 10.5, 11.5, 11, 12]:
deltas [+1, -0.5, +1, -0.5, +1]; seed avg_gain = 2/3, avg_loss = 1/6 → RSI 80
then Wilder-smoothed to 61.538... and finally 77.272... (hand-derived).
"""

import pytest

from algobots.strategies.dsl import validate_spec
from algobots.strategies.eval import (
    Bar,
    InsufficientWarmup,
    bars_from_closes,
    evaluate,
)

CROSSOVER_CLOSES = [10, 11, 12, 13, 8, 9, 11]
TREND_CLOSES = [10, 11, 12, 13, 14]
RSI_CLOSES = [10, 11, 10.5, 11.5, 11, 12]


def _spec(entry, exit_):
    return validate_spec({"version": 1, "cadence": "5m", "entry": entry, "exit": exit_})


# --- moving-average crossover (hand-checked) ----------------------------------


def test_sma_crossover_entry_fires():
    spec = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": 2}},
            "op": "crosses_above",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
        exit_={
            "left": {"indicator": "sma", "params": {"period": 2}},
            "op": "crosses_below",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
    )
    result = evaluate(spec, bars_from_closes(CROSSOVER_CLOSES))
    assert result.entry is True  # 8.5 <= 10 then 10 > 28/3
    assert result.exit is False


def test_sma4_does_not_cross_sma3_on_same_bars():
    spec = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": 4}},
            "op": "crosses_above",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
        exit_={"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
    )
    # sma4 prev 10.5 > sma3 prev 10 (no prior cross-under) and 10.25 > 28/3
    # only on the last bar — prev comparison fails, so no cross.
    assert evaluate(spec, bars_from_closes(CROSSOVER_CLOSES)).entry is False


def test_exit_crossover_fires_on_mirror_bars():
    closes = [10, 9, 8, 7, 11, 10, 9]  # mirror of the entry fixture
    # sma2 = [.., 9, 10.5, 9.5]; sma3 = [.., 8.67, 9.33, 10]
    # prev: 10.5 >= 9.33 and last: 9.5 < 10 → crosses_below
    spec = _spec(
        entry={"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
        exit_={
            "left": {"indicator": "sma", "params": {"period": 2}},
            "op": "crosses_below",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
    )
    assert evaluate(spec, bars_from_closes(closes)).exit is True


# --- threshold comparisons against hand-computed EMA/RSI ------------------------


def test_ema_threshold():
    spec = _spec(
        entry={
            "left": {"indicator": "ema", "params": {"period": 3}},
            "op": "gt",
            "right": {"value": 12.5},
        },
        exit_={"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
    )
    # ema3 last = 13 (hand-computed above) > 12.5
    assert evaluate(spec, bars_from_closes(TREND_CLOSES)).entry is True
    tighter = _spec(
        entry={
            "left": {"indicator": "ema", "params": {"period": 3}},
            "op": "gt",
            "right": {"value": 13.0},
        },
        exit_={"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
    )
    assert evaluate(tighter, bars_from_closes(TREND_CLOSES)).entry is False  # 13 > 13 is false


def test_rsi_thresholds():
    exit_ = {"left": {"source": "close"}, "op": "gt", "right": {"value": 0}}
    oversold = _spec(
        entry={
            "left": {"indicator": "rsi", "params": {"period": 3}},
            "op": "lt",
            "right": {"value": 78},
        },
        exit_=exit_,
    )
    # RSI(3) last = 77.2727... (hand-derived) < 78 → fires
    assert evaluate(oversold, bars_from_closes(RSI_CLOSES)).entry is True
    not_oversold = _spec(
        entry={
            "left": {"indicator": "rsi", "params": {"period": 3}},
            "op": "lt",
            "right": {"value": 77},
        },
        exit_=exit_,
    )
    assert evaluate(not_oversold, bars_from_closes(RSI_CLOSES)).entry is False


def test_rsi_is_100_when_never_a_loss():
    spec = _spec(
        entry={
            "left": {"indicator": "rsi", "params": {"period": 3}},
            "op": "gte",
            "right": {"value": 100},
        },
        exit_={"left": {"source": "close"}, "op": "gt", "right": {"value": 0}},
    )
    assert evaluate(spec, bars_from_closes([5, 6, 7, 8, 9])).entry is True


# --- nested AND/OR groups (depth 3) ----------------------------------------------

NESTED_ENTRY = {
    "all": [
        {  # depth 2: OR over an AND (depth 3) and a leaf
            "any": [
                {
                    "all": [
                        {
                            "left": {"indicator": "sma", "params": {"period": 2}},
                            "op": "gt",
                            "right": {"value": 0},
                        },
                        {"left": {"source": "close"}, "op": "lt", "right": {"value": 10000}},
                    ]
                },
                {
                    "left": {"indicator": "rsi", "params": {"period": 3}},
                    "op": "lt",
                    "right": {"value": 5},
                },  # deliberately false
            ]
        },
        {  # the real signal: sma2 crosses_above sma3
            "left": {"indicator": "sma", "params": {"period": 2}},
            "op": "crosses_above",
            "right": {"indicator": "sma", "params": {"period": 3}},
        },
    ]
}
EXIT_TRUE = {"left": {"source": "close"}, "op": "gt", "right": {"value": 0}}


def test_nested_and_or_depth3_true_and_falsified():
    spec = _spec(NESTED_ENTRY, EXIT_TRUE)
    assert evaluate(spec, bars_from_closes(CROSSOVER_CLOSES)).entry is True
    # Flip one leaf in the deepest AND (close > 10000, false) — entry must die.
    broken = {
        "all": NESTED_ENTRY["all"][:1]
        + [
            {
                "any": [
                    {
                        "all": [
                            {
                                "left": {"indicator": "sma", "params": {"period": 2}},
                                "op": "gt",
                                "right": {"value": 0},
                            },
                            {"left": {"source": "close"}, "op": "gt", "right": {"value": 10000}},
                        ]
                    },
                    {
                        "left": {"indicator": "rsi", "params": {"period": 3}},
                        "op": "lt",
                        "right": {"value": 5},
                    },
                ]
            }
        ]
    }
    spec_broken = _spec(broken, EXIT_TRUE)
    assert evaluate(spec_broken, bars_from_closes(CROSSOVER_CLOSES)).entry is False


def test_or_branch_rescues_a_false_and():
    entry = {
        "any": [
            {  # false: deepest AND fails (close > 10000)
                "all": [
                    {"left": {"source": "close"}, "op": "gt", "right": {"value": 10000}},
                    {"left": {"source": "close"}, "op": "lt", "right": {"value": 20000}},
                ]
            },
            {"left": {"source": "close"}, "op": "eq", "right": {"value": 11.0}},
        ]
    }
    spec = _spec(entry, EXIT_TRUE)
    assert evaluate(spec, bars_from_closes(CROSSOVER_CLOSES)).entry is True  # last close = 11


# --- sources + warmup ------------------------------------------------------------


def test_sources_beyond_close():
    bars = [
        Bar(open=1, high=2, low=0.5, close=1.5, volume=100),
        Bar(open=1.4, high=2.5, low=1.0, close=2.0, volume=300),
        Bar(open=1.9, high=3.0, low=1.4, close=2.5, volume=900),
    ]
    spec = _spec(
        entry={"left": {"source": "volume"}, "op": "gte", "right": {"value": 900}},
        exit_={"left": {"source": "high"}, "op": "lt", "right": {"value": 0}},
    )
    assert evaluate(spec, bars).entry is True


def test_insufficient_warmup_raises_purely():
    spec = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": 20}},
            "op": "crosses_above",
            "right": {"indicator": "sma", "params": {"period": 50}},
        },
        exit_=EXIT_TRUE,
    )
    with pytest.raises(InsufficientWarmup):
        evaluate(spec, bars_from_closes([1.0] * 50))  # needs 51
    evaluate(spec, bars_from_closes([1.0] * 51))  # exactly enough — no raise
