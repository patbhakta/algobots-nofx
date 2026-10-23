"""Studio draft contract and compiler (ALG-3408; slice 1 of
docs/design/strategy-studio-nautilus-bridge.md).

The browser sends a `StudioStrategyDraftV1`: strict JSON, no class paths, no
Nautilus objects, money as decimal strings. `compile_studio_strategy` turns a
complete draft into a `CompiledStrategyArtifactV1`: canonical JSON, a
deterministic `artifact_hash`, a gateway-owned implementation key from
`IMPLEMENTATIONS`, and validated Nautilus config values. Nothing in a draft
names a module or URL; only the gateway maps the key to a strategy class.

Implementation selection (gateway-owned, never author-supplied):

- `condition_dsl.v1` — deterministic mode with non-empty entry/exit; the spec
  is the existing strict DSL (`strategies/dsl.py`), so the compiled row is
  deployable through the frozen `/api/deployments` resource unchanged.
- `kalshi_momentum.v1` — deterministic mode on the Kalshi feed with no
  entry/exit: the paper loop's mom3x15m/vol20 signal, abstaining within
  `decision.min_confidence` of 0.50.

`translate_nofx_config` is the legacy path: it maps a NoFX strategy config
onto a draft per the migration map, dropping vendor-only fields with a warning
and refusing fields it cannot translate honestly (`StudioError.field` names
the owning NoFX field).
"""

from __future__ import annotations

import hashlib
import json
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    model_validator,
)

from algobots.strategies.dsl import CADENCES, SpecError, min_warmup, validate_spec

__all__ = [
    "COMPILER_VERSION",
    "IMPLEMENTATIONS",
    "CompiledStrategyArtifactV1",
    "StudioError",
    "StudioStrategyDraftV1",
    "compile_studio_strategy",
    "parse_draft",
    "translate_nofx_config",
]

COMPILER_VERSION = "studio-compiler/1"

#: Gateway-owned implementation keys -> what the key runs. Compiled artifacts
#: may only name a key from this table.
IMPLEMENTATIONS = {
    "condition_dsl.v1": "algobots.strategies.dsl:StrategySpec (frozen deployment)",
    "kalshi_momentum.v1": "algobots.demo.ledger momentum worker (mom3x15m/vol20)",
}

#: Friendly NoFX symbols we can resolve to Nautilus instrument IDs today.
NOFX_SYMBOLS = {"KXBTC15M": ("KXBTC15M.KALSHI", "prediction", "kalshi")}

# Nautilus bar step for each DSL cadence.
_BAR_STEP = {"1m": "1-MINUTE", "5m": "5-MINUTE", "15m": "15-MINUTE", "1h": "1-HOUR", "1d": "1-DAY"}

Money = Annotated[str, StringConstraints(pattern=r"^\d{1,12}(\.\d{1,2})?$")]
InstrumentId = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9/_\-^]+\.[A-Z0-9_]+$")]


class StudioError(ValueError):
    """A draft failed validation or compilation; `field` is the owning path."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"field": self.field, "message": self.message}


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class UniverseV1(_Strict):
    asset_class: Literal["equity", "fx", "crypto", "prediction"]
    symbols: list[InstrumentId] = Field(min_length=1, max_length=50)
    datafeed: Literal["ibkr", "kalshi", "pmus", "sim"]


class IndicatorV1(_Strict):
    kind: Literal["sma", "ema", "rsi"]
    period: int = Field(ge=2, le=10000)


class SignalsV1(_Strict):
    cadence: Literal["1m", "5m", "15m", "1h", "1d"]
    bars: int = Field(ge=1, le=100000)
    indicators: list[IndicatorV1] = Field(default_factory=list, max_length=20)
    # Strict DSL conditions, checked at compile: drafts may be incomplete.
    entry: dict[str, Any] = Field(default_factory=lambda: {"all": []})
    exit: dict[str, Any] = Field(default_factory=lambda: {"all": []})


class DecisionV1(_Strict):
    mode: Literal["deterministic", "prompt"] = "deterministic"
    custom_prompt: str | None = Field(default=None, max_length=8000)
    prompt_sections: dict[str, str] | None = None
    min_confidence: float | None = Field(default=None, ge=0, le=0.5)

    @model_validator(mode="after")
    def _prompt_only_in_prompt_mode(self) -> DecisionV1:
        if self.mode == "deterministic" and (self.custom_prompt or self.prompt_sections):
            raise ValueError("prompts are only allowed when mode is 'prompt'")
        return self


class RiskV1(_Strict):
    max_positions: int = Field(ge=1, le=100)
    max_order_value: Money | None = None
    max_daily_loss: Money | None = None
    max_gross_exposure: Money | None = None


class StudioStrategyDraftV1(_Strict):
    schema_version: Literal[1]
    name: str = Field(min_length=1, max_length=120)
    universe: UniverseV1
    signals: SignalsV1
    decision: DecisionV1 = Field(default_factory=DecisionV1)
    risk: RiskV1


class CompiledStrategyArtifactV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_hash: str
    compiler_version: str
    source_schema_version: int
    implementation: str
    canonical_draft: str
    nautilus: dict[str, Any]
    spec: dict[str, Any] | None  # condition_dsl.v1 only: the deployable DSL spec
    warnings: list[str]


def parse_draft(data: Any) -> StudioStrategyDraftV1:
    """Validate a draft payload (JSON mode, so decimal strings stay strings)."""
    try:
        return StudioStrategyDraftV1.model_validate_json(json.dumps(data))
    except (TypeError, ValueError) as exc:
        if not isinstance(exc, ValidationError):
            raise StudioError("draft", "not JSON-serialisable") from None
        err = exc.errors(include_url=False)[0]
        field = ".".join(str(p) for p in err["loc"]) or "draft"
        raise StudioError(field, err["msg"]) from None


def _canonical(draft: StudioStrategyDraftV1) -> str:
    return json.dumps(draft.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


def _is_empty(cond: dict[str, Any]) -> bool:
    return not cond or cond in ({"all": []}, {"any": []})


def compile_studio_strategy(draft: StudioStrategyDraftV1) -> CompiledStrategyArtifactV1:
    """Pure and deterministic: same draft + compiler version -> same hash."""
    risk = draft.risk
    for name in ("max_order_value", "max_daily_loss"):
        if getattr(risk, name) is None:
            raise StudioError(f"risk.{name}", "required before a draft can compile")
    if draft.decision.mode == "prompt":
        raise StudioError(
            "decision.mode", "prompt mode has no Phase 1 implementation; use deterministic"
        )

    sig = draft.signals
    warnings: list[str] = []
    spec: dict[str, Any] | None = None
    if not (_is_empty(sig.entry) and _is_empty(sig.exit)):
        try:
            parsed = validate_spec({"cadence": sig.cadence, "entry": sig.entry, "exit": sig.exit})
        except SpecError as exc:
            raise StudioError("signals", str(exc)) from None
        warmup = max(min_warmup(parsed), sig.bars)
        spec = validate_spec({**parsed.model_dump(mode="json"), "warmup_bars": warmup})
        spec = spec.model_dump(mode="json")
        implementation = "condition_dsl.v1"
        params: dict[str, Any] = {}
    elif draft.universe.datafeed == "kalshi":
        if draft.decision.min_confidence is None:
            raise StudioError(
                "decision.min_confidence", "the abstain band (edge from 0.50) is required"
            )
        implementation = "kalshi_momentum.v1"
        params = {"p_source": "mom3x15m/vol20", "min_edge": draft.decision.min_confidence}
        warmup = sig.bars
    else:
        raise StudioError("signals.entry", "deterministic mode needs entry and exit conditions")

    if sig.indicators and implementation == "kalshi_momentum.v1":
        warnings.append("indicator toggles are display-only for kalshi_momentum.v1")

    canonical = _canonical(draft)
    digest = hashlib.sha256(f"{COMPILER_VERSION}\n{canonical}".encode()).hexdigest()
    step = _BAR_STEP[sig.cadence]
    nautilus = {
        "instrument_ids": list(draft.universe.symbols),
        "bar_types": [f"{s}-{step}-LAST-EXTERNAL" for s in draft.universe.symbols],
        "warmup_bars": warmup,
        "datafeed": draft.universe.datafeed,
        "params": params,
        "risk_envelope": risk.model_dump(mode="json"),
    }
    return CompiledStrategyArtifactV1(
        artifact_hash=digest,
        compiler_version=COMPILER_VERSION,
        source_schema_version=draft.schema_version,
        implementation=implementation,
        canonical_draft=canonical,
        nautilus=nautilus,
        spec=spec,
        warnings=warnings,
    )


# --- legacy NoFX translation (migration map) ---------------------------------

_DROPPED = ("nofxos_api_key", "external_url", "external_headers", "api_key")


def translate_nofx_config(name: str, config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """NoFX strategy config -> draft payload + warnings; StudioError if untranslatable."""
    ai = config.get("ai_config") or {}
    if config.get("grid_config") or ai.get("grid_config"):
        raise StudioError("grid_config", "grid strategies are out of Phase 1")
    warnings = [f"{k} dropped (server-side feed binding only)" for k in _DROPPED if ai.get(k)]

    src = ai.get("coin_source") or {}
    if src.get("source_type", "static") != "static":
        raise StudioError("coin_source.source_type", "only a static symbol list is supported")
    coins = src.get("static_coins") or []
    if not coins:
        raise StudioError("coin_source.static_coins", "at least one symbol is required")
    resolved = []
    for coin in coins:
        if coin not in NOFX_SYMBOLS:
            raise StudioError("coin_source.static_coins", f"{coin} has no Nautilus instrument")
        resolved.append(NOFX_SYMBOLS[coin])
    if len({(a, f) for _, a, f in resolved}) != 1:
        raise StudioError("coin_source.static_coins", "symbols must share one feed")

    ind = ai.get("indicators") or {}
    klines = ind.get("klines") or {}
    cadence = klines.get("primary_timeframe", "15m")
    if cadence not in CADENCES:
        raise StudioError("indicators.klines.primary_timeframe", f"unsupported cadence {cadence}")
    indicators = [
        {"kind": k, "period": p} for k, p in (("ema", 20), ("rsi", 14)) if ind.get(f"enable_{k}")
    ]

    rc = ai.get("risk_control") or {}
    if any(rc.get(k) not in (None, 1) for k in ("btc_eth_max_leverage", "altcoin_max_leverage")):
        warnings.append("leverage hints dropped: never presented as enforced risk")
    worker = config.get("demo_worker") or {}
    decision: dict[str, Any] = {"mode": "deterministic"}
    if worker.get("min_edge") is not None:
        decision["min_confidence"] = float(worker["min_edge"])
        if ai.get("custom_prompt"):
            warnings.append("custom_prompt kept on the NoFX row only; deterministic mode")
    elif ai.get("custom_prompt"):
        decision = {"mode": "prompt", "custom_prompt": ai["custom_prompt"]}

    risk: dict[str, Any] = {"max_positions": int(rc.get("max_positions") or 1)}
    for k in ("max_order_value", "max_daily_loss"):
        if worker.get(k) is not None:
            risk[k] = str(worker[k])

    draft = {
        "schema_version": 1,
        "name": name,
        "universe": {
            "asset_class": resolved[0][1],
            "symbols": [r[0] for r in resolved],
            "datafeed": resolved[0][2],
        },
        "signals": {
            "cadence": cadence,
            "bars": int(klines.get("primary_count") or 20),
            "indicators": indicators,
        },
        "decision": decision,
        "risk": risk,
    }
    return draft, warnings
