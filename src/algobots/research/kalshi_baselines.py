"""Replay preserved KXBTC15M predictions and execute them with Nautilus.

The historical files contain settled binary outcomes and probabilities.  This
module deliberately keeps scoring (the evidence) separate from execution (the
Nautilus smoke test), so a missing external data mount cannot silently produce
plausible-looking synthetic results.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Prediction:
    event: str
    outcome: int
    probability: float
    ts: float


@dataclass(frozen=True)
class Score:
    name: str
    rows: int
    accuracy: float
    brier: float


PROBABILITY_KEYS = {
    "observations": "p",
    "coinflip": "p",
    "jev_backtest": "jev_p",
}


def load_predictions(
    path: Path,
    probability_key: str | None = None,
    outcomes: Mapping[str, int] | None = None,
    skip_unsettled: bool = False,
) -> list[Prediction]:
    """Load and validate a JSONL prediction file; invalid evidence fails closed."""
    key = probability_key or PROBABILITY_KEYS.get(path.stem)
    if key is None:
        raise ValueError(f"no probability key declared for {path.name}")
    rows: list[Prediction] = []
    for line_no, line in enumerate(path.read_text().splitlines(), 1):
        if not line.strip():
            continue
        raw = json.loads(line)
        if "outcome" not in raw and str(raw.get("event")) not in (outcomes or {}):
            if skip_unsettled:
                continue
            raise ValueError(f"{path}:{line_no}: prediction has no settled outcome")
        try:
            event = str(raw["event"])
            outcome = int(raw["outcome"] if "outcome" in raw else (outcomes or {})[event])
            probability = float(raw[key])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{path}:{line_no}: malformed prediction") from exc
        if outcome not in (0, 1) or not math.isfinite(probability) or not 0 <= probability <= 1:
            raise ValueError(f"{path}:{line_no}: outcome/probability outside binary bounds")
        # Old backtests did not record timestamps. Event order is stable and a
        # deterministic 15-minute clock is sufficient for offline execution.
        ts = float(raw.get("ts", 1_700_000_000 + len(rows) * 900))
        rows.append(Prediction(event, outcome, probability, ts))
    if not rows:
        raise ValueError(f"{path}: no prediction rows")
    return rows


def score(name: str, rows: Iterable[Prediction]) -> Score:
    values = list(rows)
    if not values:
        raise ValueError("cannot score an empty prediction set")
    accuracy = sum((row.probability >= 0.5) == bool(row.outcome) for row in values) / len(values)
    brier = sum((row.probability - row.outcome) ** 2 for row in values) / len(values)
    return Score(name, len(values), accuracy, brier)


def score_preserved(directory: Path) -> dict[str, Score]:
    """Score every preserved baseline independently (no accidental inner join)."""
    result = {}
    observation_path = directory / "observations.jsonl"
    observations = load_predictions(observation_path, "p") if observation_path.exists() else []
    outcomes = {row.event: row.outcome for row in observations}
    for name, key in PROBABILITY_KEYS.items():
        path = directory / f"{name}.jsonl"
        if path.exists():
            result[name] = score(name, load_predictions(path, key, outcomes))
    v2_path = directory / "predictions_v2.jsonl"
    if v2_path.exists():
        result["coinflip_v2"] = score(
            "coinflip_v2", load_predictions(v2_path, "p_coin", skip_unsettled=True)
        )
    return result


def run_nautilus(rows: Iterable[Prediction], *, account: str = "kalshi_research") -> Mapping:
    """Execute one contract per prediction in the production BacktestEngine adapter."""
    from algobots.engine.sleeve import NautilusSleeve

    values = list(rows)
    sleeve = NautilusSleeve(account, capital=__import__("decimal").Decimal(len(values) + 100))
    executions = []
    for row in values:
        side = "YES" if row.probability >= 0.5 else "NO"
        executions.append(
            sleeve.execute(row.event, side, row.ts, bool(row.outcome) == (side == "YES"), 1)
        )
    return {
        "engine": sleeve.ids,
        "rows": len(executions),
        "orders_filled": sleeve.strategy.filled,
        "ending_equity": str(sleeve.equity),
        "score": asdict(score("nautilus_observations", values)),
    }
