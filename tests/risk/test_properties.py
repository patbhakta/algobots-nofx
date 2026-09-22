"""Property tests — the risk rail's invariants hold for arbitrary inputs."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from algobots.risk.audit import InMemorySink, RiskGate
from algobots.risk.envelopes import RiskEnvelope
from algobots.risk.limits import RiskLimits, apply_limits

ENVELOPE = RiskEnvelope(max_order_value=Decimal("1000"), max_daily_loss=Decimal("500"))

ticker_names = st.text(
    alphabet=st.characters(min_codepoint=65, max_codepoint=90), min_size=1, max_size=4
)
arbitrary_weights = st.dictionaries(
    keys=ticker_names,
    values=st.floats(min_value=-10.0, max_value=10.0, allow_nan=False, allow_infinity=False),
    max_size=8,
)
arbitrary_limits = st.builds(
    RiskLimits,
    max_position_pct=st.floats(min_value=0.01, max_value=1.0),
    max_gross_exposure=st.floats(min_value=0.01, max_value=10.0),
)


@given(weights=arbitrary_weights, limits=arbitrary_limits)
@settings(max_examples=300, deadline=None)
def test_clamping_never_increases_exposure(weights, limits):
    """Per-ticker |weight| and gross Σ|weights| are non-increasing."""
    result = apply_limits(weights, limits)
    for ticker, w in result.weights.items():
        assert abs(w) <= abs(weights[ticker]) + 1e-9
    gross_before = sum(abs(w) for w in weights.values())
    gross_after = sum(abs(w) for w in result.weights.values())
    assert gross_after <= gross_before + 1e-9


@given(weights=arbitrary_weights, limits=arbitrary_limits)
@settings(max_examples=300, deadline=None)
def test_clamp_order_is_idempotent(weights, limits):
    """Per-ticker → gross, applied twice, equals applied once.

    Tolerance is float-ulp level only: the second pass can at worst
    re-scale the gross cap by a rounding ulp; the per-ticker pass can
    never re-fire (|w| ≤ cap exactly after the first pass).
    """
    once = apply_limits(weights, limits)
    twice = apply_limits(once.weights, limits)
    assert set(twice.weights) == set(once.weights)
    for ticker, w in once.weights.items():
        assert twice.weights[ticker] == pytest.approx(w, abs=1e-12)
    for clamp in twice.clamps:
        assert clamp.limit == "max_gross_exposure"
        assert abs(clamp.before - clamp.after) < 1e-9


@given(weights=arbitrary_weights, limits=arbitrary_limits)
@settings(max_examples=300, deadline=None)
def test_every_firing_emits_exactly_one_row(weights, limits):
    """Row count == firing count, 1:1, for arbitrary books."""
    sink = InMemorySink()
    gate = RiskGate(
        limits=limits,
        envelope=ENVELOPE,
        sink=sink,
        now=lambda: "2026-09-22T00:00:00+00:00",
    )
    result = gate.apply_weights(weights, deployment_id="prop")
    assert len(sink.rows) == len(result.clamps)
    for row, clamp in zip(sink.rows, result.clamps):
        assert row.source == "limits"
        assert row.limit == clamp.limit
        assert row.ticker == clamp.ticker
        assert row.deployment_id == "prop"
        assert row.before == pytest.approx(clamp.before)
        assert row.after == pytest.approx(clamp.after)
