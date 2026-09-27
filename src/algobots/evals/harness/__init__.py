"""Decision-quality harness: prospective decisions, settled outcomes, scored honestly.

Protocol sources: ALG-3074 (TradingAgents backtest shape), ALG-3075 jev_stock
(calibration protocol: threshold-explicit labels, Brier, Wilson 95% CIs,
prospective-only scoring for anything that gates money).
"""

from .baselines import (
    AlwaysFlatBaseline,
    RandomBaseline,
    baseline_summaries,
    chance_level,
    persistence_baseline,
    random_at_or_below_chance,
)
from .grid import CorruptStateError, GridCell, GridRunStats, SkipCell, load_checkpoint, run_grid
from .records import DIRECTION_BANDS, DecisionRecord, MoneyGateError, SettlementCorrection
from .report import render_json, render_markdown
from .scoring import BandScore, HarnessSummary, multiclass_brier, summarize, wilson_interval

__all__ = [
    "DIRECTION_BANDS",
    "DecisionRecord",
    "MoneyGateError",
    "SettlementCorrection",
    "BandScore",
    "HarnessSummary",
    "multiclass_brier",
    "summarize",
    "wilson_interval",
    "AlwaysFlatBaseline",
    "RandomBaseline",
    "baseline_summaries",
    "chance_level",
    "persistence_baseline",
    "random_at_or_below_chance",
    "GridCell",
    "GridRunStats",
    "SkipCell",
    "CorruptStateError",
    "load_checkpoint",
    "run_grid",
    "render_json",
    "render_markdown",
]
