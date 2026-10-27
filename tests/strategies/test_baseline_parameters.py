"""Baseline identity, parameter persistence, and no-lookahead entry boundaries."""

import copy
import hashlib
import json

import pytest

from algobots.strategies.backtest import baseline_signal
from algobots.strategies.studio import (
    StudioError,
    compile_studio_strategy,
    parse_draft,
    translate_nofx_config,
)
from tests.strategies.test_studio import NOFX_MOMENTUM


def artifact(baseline):
    config = {**copy.deepcopy(NOFX_MOMENTUM), "baseline": baseline}
    draft, _ = translate_nofx_config("Baseline", config)
    return compile_studio_strategy(parse_draft(draft)).model_dump(mode="json")


@pytest.mark.parametrize(
    "baseline,implementation",
    [
        ({"strategy": "laya", "min_edge": 0.1}, "kalshi_momentum.v1"),
        ({"strategy": "coin", "entry_delay_seconds": 30, "stake": "10.00"}, "kalshi_coin.v1"),
        ({"strategy": "jev", "min_confidence": 0.8}, "kalshi_jev.v1"),
    ],
)
def test_identity_and_frozen_params(baseline, implementation):
    compiled = artifact(baseline)
    assert compiled["implementation"] == implementation
    assert compiled == artifact(baseline)
    assert json.loads(compiled["canonical_draft"])["baseline"] == baseline
    edited = dict(baseline)
    key = next(k for k in edited if k != "strategy")
    edited[key] = {"min_edge": 0.2, "entry_delay_seconds": 60, "min_confidence": 0.9}[key]
    assert artifact(edited)["artifact_hash"] != compiled["artifact_hash"]


@pytest.mark.parametrize(
    "baseline",
    [
        {"strategy": "coin", "entry_delay_seconds": 900},
        {"strategy": "coin", "stake": "0.00"},
        {"strategy": "coin", "stake": 10.0},
        {"strategy": "coin", "entry_delay_seconds": 1.5},
        {"strategy": "laya", "min_edge": -0.1},
        {"strategy": "jev", "min_confidence": 1.1},
        {"strategy": "unknown"},
        {"strategy": "jev", "model_url": "https://example.com"},
    ],
)
def test_reject_invalid_baseline(baseline):
    with pytest.raises(StudioError, match="baseline"):
        artifact(baseline)


def test_coin_delay_uses_observation_time_and_never_fabricates_later_book():
    a = artifact({"strategy": "coin", "entry_delay_seconds": 30, "stake": "12.00"})
    row = {"event": "event", "open_ts": 1000, "close_ts": 1900, "ts": 1029}
    assert baseline_signal(a, row)[1] is None
    p, side, stake = baseline_signal(a, {**row, "ts": 1030})
    assert p == 0.5 and side in ("YES", "NO") and str(stake) == "12.00"
    assert baseline_signal(a, {**row, "ts": 1900})[1] is None


def test_jev_requires_timestamped_preclose_call_and_confidence():
    a = artifact({"strategy": "jev", "min_confidence": 0.8})
    row = {
        "event": "event",
        "open_ts": 1000,
        "close_ts": 1900,
        "ts": 1050,
        "jev_ts": 1040,
        "jev_conf": 0.9,
        "jev_p": 0.7,
        "jev_choice": "up",
    }
    assert baseline_signal(a, row)[1] == "YES"
    for patch in (
        {"jev_ts": None},
        {"jev_ts": 1051},
        {"jev_ts": 999},
        {"jev_conf": 0.7},
        {"jev_choice": None},
    ):
        assert baseline_signal(a, {**row, **patch})[1] is None


def test_legacy_artifact_hashes_stay_valid():
    config = copy.deepcopy(NOFX_MOMENTUM)
    payload, _ = translate_nofx_config("Legacy", config)
    draft = parse_draft(payload)
    legacy = draft.model_dump(mode="json")
    legacy.pop("baseline")
    canonical = json.dumps(legacy, sort_keys=True, separators=(",", ":"))
    expected = hashlib.sha256(f"studio-compiler/1\n{canonical}".encode()).hexdigest()
    assert compile_studio_strategy(draft).artifact_hash == expected
