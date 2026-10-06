import math

import pytest

from algobots.evals.harness import DecisionRecord, SettlementCorrection, summarize


def _record(
    decision_id,
    band,
    probs,
    realized=None,
    benchmark=None,
    settled=False,
    ticker="X",
    trade_date="2026-09-01",
):
    r = DecisionRecord(
        decision_id=decision_id,
        ticker=ticker,
        trade_date=trade_date,
        band=band,
        probabilities=probs,
        horizon_days=1,
        preregistered_at="2026-09-01T00:00:00+00:00",
    )
    if settled:
        r.settle(realized_return=realized, benchmark_return=benchmark)
    return r


def test_wilson_known_value():
    from algobots.evals.harness import wilson_interval

    assert wilson_interval(0, 0) is None
    low, high = wilson_interval(5, 10)
    assert math.isclose(low, 0.2366, abs_tol=1e-3)
    assert math.isclose(high, 0.7634, abs_tol=1e-3)
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and 0.0 < high < 0.35


def test_realized_band_uses_explicit_threshold():
    r = _record("1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0}, settled=True, realized=0.002)
    assert summarize([r], flat_threshold=0.003).per_band["up"].correct == 0
    assert summarize([r], flat_threshold=0.001).per_band["up"].correct == 1


def test_unsettled_records_are_neither_win_nor_loss():
    settled = _record(
        "1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0}, settled=True, realized=0.05, benchmark=0.0
    )
    pending = _record("2", "down", {"up": 0.0, "flat": 0.0, "down": 1.0})
    summary = summarize([settled, pending])
    assert summary.overall.count == 1
    assert summary.overall.correct == 1
    assert summary.unsettled == 1


def test_brier_perfect_and_uniform():
    perfect = _record("1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0}, settled=True, realized=0.05)
    assert summarize([perfect]).brier == pytest.approx(0.0)
    uniform = _record(
        "2", "up", {"up": 1 / 3, "flat": 1 / 3, "down": 1 / 3}, settled=True, realized=0.05
    )
    assert summarize([uniform]).brier == pytest.approx(2.0 / 3.0)


def test_mean_alpha_against_benchmark():
    records = [
        _record(
            "1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0},
            settled=True, realized=0.05, benchmark=0.01,
        ),
        _record(
            "2", "down", {"down": 1.0, "flat": 0.0, "up": 0.0},
            settled=True, realized=-0.02, benchmark=0.00,
        ),
    ]
    summary = summarize(records)
    assert summary.overall.mean_alpha == pytest.approx((0.04 + -0.02) / 2)


def test_settlement_is_append_only():
    r = _record(
        "1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0},
        settled=True, realized=0.05, benchmark=0.01,
    )
    with pytest.raises(ValueError, match="already settled"):
        r.settle(realized_return=0.99)
    r.correct(realized_return=0.06, benchmark_return=0.01, reason="late price correction")
    assert r.effective_realized_return == pytest.approx(0.06)
    assert len(r.corrections) == 1
    assert isinstance(r.corrections[0], SettlementCorrection)
    assert r.realized_return == pytest.approx(0.05)


def test_invalid_records_rejected():
    with pytest.raises(ValueError, match="not in bands"):
        _record("1", "sideways", {"up": 1.0, "flat": 0.0, "down": 0.0})
    with pytest.raises(ValueError, match="finite"):
        _record("2", "up", {"up": float("nan"), "flat": 0.0, "down": 0.0})
    with pytest.raises(ValueError, match="trade_date"):
        _record("3", "up", {"up": 1.0, "flat": 0.0, "down": 0.0}, trade_date="09/01/2026")


def _perfect_record(i, band, realized):
    probs = {"up": 0.0, "flat": 0.0, "down": 0.0}
    probs[band] = 1.0
    return _record(str(i), band, probs, settled=True, realized=realized, benchmark=0.0)


def test_majority_label_baseline_certifies_real_edge():
    """Line B port: perfect predictions over mixed labels certify (Wilson low clears baseline)."""
    specs = [
        ("up", 0.05), ("up", 0.04), ("up", 0.06),
        ("flat", 0.0), ("flat", 0.001),
        ("down", -0.05),
    ]
    records = [_perfect_record(i, band, realized) for i, (band, realized) in enumerate(specs)]
    summary = summarize(records)
    assert summary.baseline_hit_rate == pytest.approx(0.5), "3 up-labels of 6 settled cells"
    assert summary.base_rates["up"] == pytest.approx(0.5)
    assert summary.overall.hit_rate == 1.0
    assert summary.overall.ci_low > 0.5
    assert summary.edge_demonstrated is True
    assert summary.overall.beats_baseline is True


def test_known_random_control_never_certified():
    """Line B port: random predictions never certify vs the majority-label baseline."""
    import random

    rng = random.Random(7)
    labels = ("up", "flat", "down")
    moves = {"up": 0.05, "flat": 0.0, "down": -0.05}
    records = []
    for i in range(30):
        band = rng.choice(labels)
        r = _record(
            f"r{i}",
            band,
            {b: 1 / 3 for b in labels},
            settled=True,
            realized=moves[rng.choice(labels)],
        )
        records.append(r)
    summary = summarize(records)
    assert summary.edge_demonstrated is False
    assert all(s.beats_baseline is False for s in summary.per_band.values() if s.count)


def test_certification_fields_in_summary_dict():
    payload = summarize([_perfect_record(1, "up", 0.05)]).to_dict()
    assert payload["baseline_hit_rate"] == 1.0, "single-label set: majority label is itself"
    assert payload["base_rates"] == {"up": 1.0}
    assert payload["edge_demonstrated"] is False, "Wilson low of 1/1 is below 1.0"
    assert payload["overall"]["beats_baseline"] is False


def test_empty_and_unsettlement_yield_uncertified():
    summary = summarize([])
    assert summary.baseline_hit_rate is None
    assert summary.edge_demonstrated is None
    pending = _record("1", "up", {"up": 1.0, "flat": 0.0, "down": 0.0})
    assert summarize([pending]).edge_demonstrated is None
