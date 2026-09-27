"""Condition JSON DSL for strategies (S4.2 — ALG-3091).

A strategy spec is a strictly-validated JSON document:

```json
{
  "version": 1,
  "cadence": "5m",
  "entry": {"all": [
    {"left": {"indicator": "sma", "params": {"period": 20}},
     "op": "crosses_above",
     "right": {"indicator": "sma", "params": {"period": 50}}},
    {"any": [
      {"left": {"indicator": "rsi", "params": {"period": 14}},
       "op": "lt", "right": {"value": 30}}
    ]}
  ]},
  "exit": {"left": {"indicator": "sma", "params": {"period": 20}},
           "op": "crosses_below",
           "right": {"indicator": "sma", "params": {"period": 50}}}
}
```

Validation is STRICT: unknown indicators, unknown parameter keys, unknown
operators, unknown cadences, and unknown top-level fields are all rejected
(`extra="forbid"` everywhere). Indicator parameters are typed (`period` is an
`int >= 2`). Every series reference implies a warmup requirement; the spec's
optional `warmup_bars` must cover the computed minimum.

The artifact hash (`artifact_hash`) is the sha256 of the canonical JSON dump
of the validated spec — deployments freeze spec + hash at deploy time, so a
later strategy edit can never drift into a running deployment.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

__all__ = [
    "CADENCES",
    "OPS",
    "SPEC_KIND",
    "Condition",
    "ConditionGroup",
    "ConditionLeaf",
    "SeriesRef",
    "StrategySpec",
    "SpecError",
    "artifact_hash",
    "canonical_json",
    "min_warmup",
    "validate_spec",
    "warmup",
]

#: Strategy rows whose `kind` equals this value carry a `params` payload that
#: must parse as a `StrategySpec`.
SPEC_KIND = "condition_dsl"

CADENCES = ("1m", "5m", "15m", "1h", "1d")
OPS = ("gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below")
INDICATORS = ("sma", "ema", "rsi")
SOURCES = ("open", "high", "low", "close", "volume")

Cadence = Literal["1m", "5m", "15m", "1h", "1d"]
Operator = Literal["gt", "gte", "lt", "lte", "eq", "crosses_above", "crosses_below"]
Source = Literal["open", "high", "low", "close", "volume"]
Indicator = Literal["sma", "ema", "rsi"]


class SpecError(ValueError):
    """A strategy spec failed strict validation. Message is user-presentable."""


class IndicatorParams(BaseModel):
    """Typed indicator parameters. `period` is required; unknown keys reject."""

    model_config = ConfigDict(extra="forbid")

    period: int = Field(ge=2, le=10000)


class SeriesRef(BaseModel):
    """One series to compare: a raw bar source, or an indicator over it."""

    model_config = ConfigDict(extra="forbid")

    source: Source = "close"
    indicator: Indicator | None = None
    params: IndicatorParams | None = None

    @model_validator(mode="after")
    def _params_iff_indicator(self) -> SeriesRef:
        if self.indicator is None and self.params is not None:
            raise ValueError("params are only valid when 'indicator' is set")
        if self.indicator is not None and self.params is None:
            raise ValueError(f"indicator '{self.indicator}' requires params {{'period': int}}")
        return self


class ValueOperand(BaseModel):
    """A constant comparison target."""

    model_config = ConfigDict(extra="forbid")

    value: float


Operand = ValueOperand | SeriesRef


class ConditionLeaf(BaseModel):
    """`left <op> right` where right is a constant or another series."""

    model_config = ConfigDict(extra="forbid")

    left: SeriesRef
    op: Operator
    right: Operand


class ConditionGroup(BaseModel):
    """AND (`all`) / OR (`any`) over nested conditions — exactly one key."""

    model_config = ConfigDict(extra="forbid")

    all: list[Condition] | None = None
    any: list[Condition] | None = None

    @model_validator(mode="after")
    def _exactly_one_nonempty(self) -> ConditionGroup:
        if (self.all is None) == (self.any is None):
            raise ValueError("a group must set exactly one of 'all' or 'any'")
        if not (self.all or self.any):
            raise ValueError("a group must not be empty")
        return self


Condition = ConditionLeaf | ConditionGroup


class StrategySpec(BaseModel):
    """The full strategy DSL document stored in `strategies.params_json`."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    cadence: Cadence
    entry: Condition
    exit: Condition
    warmup_bars: int | None = Field(default=None, ge=1, le=100000)

    @model_validator(mode="after")
    def _warmup_floor(self) -> StrategySpec:
        needed = max(_condition_warmup(self.entry), _condition_warmup(self.exit))
        if self.warmup_bars is not None and self.warmup_bars < needed:
            raise ValueError(f"warmup_bars={self.warmup_bars} is below the required {needed}")
        return self


ConditionLeaf.model_rebuild()
ConditionGroup.model_rebuild()
StrategySpec.model_rebuild()


# --- warmup -----------------------------------------------------------------


def _series_warmup(ref: SeriesRef) -> int:
    """Bars a series reference needs before it is defined."""
    if ref.indicator is None:
        return 1
    period = ref.params.period if ref.params else 2
    if ref.indicator == "rsi":
        return period + 1  # p deltas need p + 1 closes
    return period  # sma / ema seed on the first `period` bars


def _operand_warmup(operand: Operand) -> int:
    if isinstance(operand, ValueOperand):
        return 1
    return _series_warmup(operand)


def _condition_warmup(condition: Condition) -> int:
    """Bars a condition needs before it can be evaluated."""
    if isinstance(condition, ConditionLeaf):
        left = _series_warmup(condition.left)
        right = _operand_warmup(condition.right)
        if condition.op in ("crosses_above", "crosses_below"):
            return max(left, right) + 1  # needs the previous bar too
        return max(left, right)
    children = condition.all or condition.any or []
    return max((_condition_warmup(child) for child in children), default=1)


def warmup(condition: Condition) -> int:
    """Public wrapper for one condition subtree's warmup requirement."""
    return _condition_warmup(condition)


def min_warmup(spec: StrategySpec) -> int:
    """Minimum bars before the spec's entry/exit conditions are defined."""
    return max(_condition_warmup(spec.entry), _condition_warmup(spec.exit))


# --- canonical form + artifact hash ------------------------------------------


def canonical_json(spec: StrategySpec) -> str:
    """Canonical JSON: sorted keys, no whitespace — the freezable artifact."""
    return json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def artifact_hash(spec: StrategySpec) -> str:
    """sha256 hex of the canonical spec — the frozen deployment's identity."""
    return hashlib.sha256(canonical_json(spec).encode("utf-8")).hexdigest()


# --- validation entry point ---------------------------------------------------


def validate_spec(data: Mapping[str, Any] | str) -> StrategySpec:
    """Strictly validate a spec payload; raises SpecError with a clean message."""
    try:
        if isinstance(data, str):
            return StrategySpec.model_validate_json(data)
        return StrategySpec.model_validate(dict(data))
    except ValidationError as exc:
        raise SpecError(_flatten(exc)) from None


def _flatten(exc: ValidationError) -> str:
    parts: list[str] = []
    for error in exc.errors(include_url=False):
        location = ".".join(str(piece) for piece in error["loc"]) or "spec"
        parts.append(f"{location}: {error['msg']}")
    return "; ".join(parts)
