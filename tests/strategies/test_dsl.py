"""DSL strict-validation tests (AC 1 — typed params, warmup, artifact hash).

Unknown indicators, unknown params, unknown operators, unknown cadences, and
unknown fields must all reject; warmup requirements must be computed exactly;
the artifact hash must be canonical (key-order independent) and stable.
"""

import pytest

from algobots.strategies.dsl import (
    SpecError,
    artifact_hash,
    canonical_json,
    min_warmup,
    validate_spec,
)

VALID = {
    "version": 1,
    "cadence": "5m",
    "entry": {
        "left": {"indicator": "sma", "params": {"period": 20}},
        "op": "crosses_above",
        "right": {"indicator": "sma", "params": {"period": 50}},
    },
    "exit": {
        "left": {"indicator": "rsi", "params": {"period": 14}},
        "op": "gt",
        "right": {"value": 70},
    },
}


def _spec(**overrides) -> dict:
    spec = {**VALID, **overrides}
    return spec


# --- strict validation: unknown anything rejects -----------------------------


def test_valid_spec_parses():
    spec = validate_spec(_spec())
    assert spec.cadence == "5m"
    assert spec.entry.left.indicator == "sma"
    assert spec.entry.left.params.period == 20


def test_unknown_indicator_rejects():
    bad = _spec(
        entry={
            "left": {"indicator": "hma", "params": {"period": 20}},
            "op": "gt",
            "right": {"value": 1},
        }
    )
    with pytest.raises(SpecError, match="indicator"):
        validate_spec(bad)


def test_unknown_param_key_rejects():
    bad = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": 20, "span": 3}},
            "op": "gt",
            "right": {"value": 1},
        }
    )
    with pytest.raises(SpecError):
        validate_spec(bad)


def test_period_must_be_typed_int():
    bad = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": "twenty"}},
            "op": "gt",
            "right": {"value": 1},
        }
    )
    with pytest.raises(SpecError):
        validate_spec(bad)
    too_small = _spec(
        entry={
            "left": {"indicator": "sma", "params": {"period": 1}},
            "op": "gt",
            "right": {"value": 1},
        }
    )
    with pytest.raises(SpecError):
        validate_spec(too_small)


def test_indicator_requires_params_and_vice_versa():
    with pytest.raises(SpecError):
        validate_spec(
            _spec(
                entry={"left": {"indicator": "sma"}, "op": "gt", "right": {"value": 1}},
                exit=_spec()["entry"],
            )
        )
    with pytest.raises(SpecError):
        validate_spec(
            _spec(
                entry={"left": {"params": {"period": 5}}, "op": "gt", "right": {"value": 1}},
                exit=_spec()["entry"],
            )
        )


def test_unknown_operator_rejects():
    bad = _spec(entry={"left": {"source": "close"}, "op": "above", "right": {"value": 1}})
    with pytest.raises(SpecError):
        validate_spec(bad)


def test_unknown_cadence_rejects():
    with pytest.raises(SpecError):
        validate_spec(_spec(cadence="7m"))


def test_unknown_version_rejects():
    with pytest.raises(SpecError):
        validate_spec(_spec(version=2))


def test_unknown_top_level_field_rejects():
    with pytest.raises(SpecError):
        validate_spec({**_spec(), "leverage": 10})


def test_missing_exit_rejects():
    spec = _spec()
    del spec["exit"]
    with pytest.raises(SpecError):
        validate_spec(spec)


def test_group_must_set_exactly_one_of_all_any():
    leaf = {"left": {"source": "close"}, "op": "gt", "right": {"value": 1}}
    with pytest.raises(SpecError):  # both
        validate_spec(_spec(entry={"all": [leaf], "any": [leaf]}, exit=leaf))
    with pytest.raises(SpecError):  # neither
        validate_spec(_spec(entry={"all": [leaf], "any": []}, exit=leaf))
    with pytest.raises(SpecError):  # empty group
        validate_spec(_spec(entry={"any": []}, exit=leaf))


def test_validate_spec_accepts_json_string():
    import json

    spec = validate_spec(json.dumps(_spec()))
    assert spec.cadence == "5m"


# --- warmup requirements ------------------------------------------------------


def test_warmup_computed_exactly():
    # SMA(20) vs SMA(50) cross needs max(20, 50) + 1 bars; RSI(14) needs 15.
    spec = validate_spec(_spec())
    assert min_warmup(spec) == 51


def test_warmup_raw_source_is_one_bar():
    spec = validate_spec(
        _spec(
            entry={"left": {"source": "close"}, "op": "gt", "right": {"value": 1}},
            exit={"left": {"source": "low"}, "op": "lt", "right": {"value": 1}},
        )
    )
    assert min_warmup(spec) == 1


def test_warmup_bars_floor_enforced():
    spec = _spec(warmup_bars=3)  # below the required 51
    with pytest.raises(SpecError, match="warmup"):
        validate_spec(spec)
    ok = validate_spec(_spec(warmup_bars=51))
    assert ok.warmup_bars == 51


# --- artifact hash -------------------------------------------------------------


def test_artifact_hash_is_canonical_and_stable():
    spec = validate_spec(_spec())
    reordered = validate_spec(
        {
            "exit": VALID["exit"],
            "entry": VALID["entry"],
            "cadence": "5m",
            "version": 1,
        }
    )
    assert canonical_json(spec) == canonical_json(reordered)
    assert artifact_hash(spec) == artifact_hash(reordered)
    assert len(artifact_hash(spec)) == 64


def test_artifact_hash_changes_with_params():
    base = validate_spec(_spec())
    edited = validate_spec(
        _spec(
            entry={
                "left": {"indicator": "sma", "params": {"period": 21}},
                "op": "crosses_above",
                "right": {"indicator": "sma", "params": {"period": 50}},
            }
        )
    )
    assert artifact_hash(base) != artifact_hash(edited)
