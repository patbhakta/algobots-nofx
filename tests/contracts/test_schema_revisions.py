"""A01 acceptance case 3: a schema revision cannot silently invalidate a queued packet."""

import json
import re
import runpy
import sys
from pathlib import Path
from typing import Annotated, ClassVar

import pytest
from pydantic import Field, model_validator

from algobots.contracts import Signal, registry

REPO_ROOT = Path(__file__).resolve().parents[2]
MAP = json.loads((REPO_ROOT / "docs" / "repository-map.json").read_text())
PINS = {pid: p["contract_pins"] for pid, p in MAP["packets"].items()}
SIGNAL = json.loads((Path(__file__).parent / "golden/valid/Signal@1.0.json").read_text())


def test_lock_matches_registry():
    assert registry.verify_lock(registry.load_lock()) == []


def test_every_queued_pin_resolves():
    registry.check_pins(PINS, registry.load_lock())


def test_shape_change_without_version_bump_is_detected(monkeypatch):
    class MutatedSignal(Signal):
        sneaky: int = 0

    monkeypatch.setitem(registry._REGISTRY, ("Signal", "1.0"), MutatedSignal)
    problems = registry.verify_lock(registry.load_lock())
    expected = "Signal@1.0 changed schema or validators without a version bump"
    assert any(expected in p for p in problems)


def test_validator_tightening_without_schema_change_is_detected(monkeypatch):
    """A2: the JSON schema omits validator logic; the fingerprint must not."""
    from algobots.contracts import TargetPortfolio as Locked

    class TargetPortfolio(Locked):
        __doc__ = Locked.__doc__

        @model_validator(mode="after")
        def _weights(self):
            return self

    assert TargetPortfolio.model_json_schema() == Locked.model_json_schema()
    monkeypatch.setitem(registry._REGISTRY, ("TargetPortfolio", "1.0"), TargetPortfolio)
    problems = registry.verify_lock(registry.load_lock())
    assert any(p.startswith("TargetPortfolio@1.0 changed") for p in problems)


def test_editing_a_shared_validator_helper_is_detected(monkeypatch):
    """Helpers and constants that validators reference are part of the fingerprint."""
    from algobots.contracts import base, plan

    def _order_action(value):  # looser: accepts CREATE_TARGET
        return value

    monkeypatch.setattr(plan, "_order_action", _order_action)
    monkeypatch.setattr(base, "_DECIMAL_TEXT", re.compile(r"[0-9.]+"))
    drifted = {p.split("@")[0] for p in registry.verify_lock(registry.load_lock())}
    assert {"OrderPlan", "ExecutionCommand", "ApprovalEnvelope"} <= drifted


def test_in_place_lock_regeneration_fails_the_transition_check(monkeypatch, capsys):
    """A1: tighten Signal@1.0 in place and rewrite the lock; verify-A01 must still fail."""

    class TighterSignal(Signal):
        horizon: Annotated[str, Field(pattern=r"^\d+(d)$")]

    committed = registry.load_lock()
    monkeypatch.setitem(registry._REGISTRY, ("Signal", "1.0"), TighterSignal)
    monkeypatch.setattr(registry, "load_lock", registry.current_lock)  # as after --write-lock
    monkeypatch.setattr(registry, "load_lock_at", lambda ref: committed)
    monkeypatch.setattr(sys, "argv", ["algobots.contracts", "--check-transition", "base"])
    with pytest.raises(SystemExit) as exc:
        runpy.run_module("algobots.contracts", run_name="__main__")
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert "schema lock in sync" in out  # the lock alone no longer catches it
    assert "Signal@1.0 fingerprint rewritten in place" in out


def test_rewriting_a_locked_fingerprint_is_rejected():
    old = registry.load_lock()
    new = json.loads(json.dumps(old))
    new["Signal"]["1.0"] = "0" * 64
    with pytest.raises(registry.SchemaRevisionError, match="Signal@1.0 fingerprint rewritten"):
        registry.check_lock_transition(old, new, PINS)


def test_removing_a_pinned_version_names_the_stranded_packets():
    old = registry.load_lock()
    new = json.loads(json.dumps(old))
    del new["Signal"]["1.0"]
    with pytest.raises(registry.SchemaRevisionError) as exc:
        registry.check_lock_transition(old, new, PINS)
    assert "Signal@1.0 removed while queued packets pin it: A18, A19, A20, A28" in str(exc.value)
    with pytest.raises(registry.SchemaRevisionError, match="unresolvable contract pins"):
        registry.check_pins(PINS, new)


def test_additive_revision_keeps_queued_payloads_valid(monkeypatch):
    class SignalV2(Signal):
        contract_version: ClassVar[str] = "2.0"
        regime_id: str

    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    registry.register(SignalV2)
    old = registry.load_lock()
    new = registry.current_lock()
    registry.check_lock_transition(old, new, PINS)  # adding 2.0 is allowed

    assert type(registry.parse("Signal", SIGNAL)) is Signal  # queued 1.0 payload still parses
    v2 = registry.parse("Signal", {**SIGNAL, "schema_version": "2.0", "regime_id": "r1"})
    assert isinstance(v2, SignalV2)
    with pytest.raises(ValueError, match="schema_version '1.0' is not '2.0'"):
        SignalV2.model_validate({**SIGNAL, "regime_id": "r1"})


def test_removing_an_unpinned_version_is_allowed():
    old = {"Legacy": {"0.9": "a" * 64}, **registry.load_lock()}
    registry.check_lock_transition(old, registry.load_lock(), PINS)


def test_unresolvable_transition_base_is_an_error():
    """N1 (ALG-3176): a mistyped base must not pass as a first introduction."""
    with pytest.raises(registry.SchemaRevisionError, match="'no-such-ref' is not a commit"):
        registry.load_lock_at("no-such-ref")
