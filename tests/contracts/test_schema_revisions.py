"""A01 acceptance case 3: a schema revision cannot silently invalidate a queued packet."""

import json
from pathlib import Path
from typing import ClassVar

import pytest

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
    assert any("Signal@1.0 changed shape without a version bump" in p for p in problems)


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
