"""Strategy condition DSL: schema, validation, pure evaluation (S4.2 — ALG-3091).

Public surface:
- `dsl` — strict spec schema (`StrategySpec`), warmup computation, canonical
  JSON + `artifact_hash`
- `eval` — pure `evaluate(spec, bars)` over indicator windows (no I/O)
"""

from algobots.strategies.dsl import (
    CADENCES,
    OPS,
    SPEC_KIND,
    Condition,
    ConditionGroup,
    ConditionLeaf,
    SeriesRef,
    SpecError,
    StrategySpec,
    ValueOperand,
    artifact_hash,
    canonical_json,
    min_warmup,
    validate_spec,
    warmup,
)
from algobots.strategies.eval import (
    Bar,
    Evaluation,
    InsufficientWarmup,
    bars_from_closes,
    evaluate,
)

__all__ = [
    "CADENCES",
    "OPS",
    "SPEC_KIND",
    "Bar",
    "Condition",
    "ConditionGroup",
    "ConditionLeaf",
    "Evaluation",
    "InsufficientWarmup",
    "SeriesRef",
    "SpecError",
    "StrategySpec",
    "ValueOperand",
    "artifact_hash",
    "bars_from_closes",
    "canonical_json",
    "evaluate",
    "min_warmup",
    "validate_spec",
    "warmup",
]
