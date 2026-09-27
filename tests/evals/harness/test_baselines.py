from algobots.evals.harness import (
    AlwaysFlatBaseline,
    DecisionRecord,
    RandomBaseline,
    chance_level,
    persistence_baseline,
    random_at_or_below_chance,
    summarize,
)
from algobots.evals.harness.grid import trading_dates_back_from


def _synthetic_settled(n=2400, seed=7):
    """Symmetric three-class synthetic market: realized band is uniform by construction."""
    import random

    rng = random.Random(seed)
    dates = trading_dates_back_from("2026-09-18", n)
    records = []
    for i, trade_date in enumerate(dates):
        realized = rng.choice([0.05, 0.0, -0.05])
        r = DecisionRecord(
            decision_id=f"synth-{i}",
            ticker="SYN",
            trade_date=trade_date,
            band="flat",
            probabilities={"up": 1 / 3, "flat": 1 / 3, "down": 1 / 3},
            horizon_days=1,
            preregistered_at="2026-01-01T00:00:00+00:00",
        )
        r.settle(realized_return=realized, benchmark_return=0.0)
        records.append(r)
    return records


def test_random_baseline_is_deterministic():
    a = RandomBaseline(seed=11)
    b = RandomBaseline(seed=11)
    assert a.predict("BTC", "2026-09-01") == b.predict("BTC", "2026-09-01")


def test_random_baseline_reproduces_at_or_below_chance():
    """Q&A gate: a known-random predictor scores at <= chance, honestly."""
    rng_bands = ("up", "flat", "down")
    dates = trading_dates_back_from("2026-09-18", 2400)
    synthetic = _synthetic_settled(len(dates))
    baseline = RandomBaseline(seed=3)
    baseline_records = []
    for i, record in enumerate(synthetic):
        band, probs = baseline.predict(record.ticker, record.trade_date)
        r = DecisionRecord(
            decision_id=f"rand-{i}",
            ticker=record.ticker,
            trade_date=record.trade_date,
            band=band,
            probabilities=probs,
            horizon_days=1,
            preregistered_at="2026-01-01T00:00:00+00:00",
        )
        r.settle(realized_return=record.realized_return, benchmark_return=0.0)
        baseline_records.append(r)
    summary = summarize(baseline_records, flat_threshold=0.003)
    assert random_at_or_below_chance(summary, tolerance=0.01)
    s2 = summarize(baseline_records)
    ci_low, ci_high = s2.overall.ci_low, s2.overall.ci_high
    assert ci_low <= chance_level(rng_bands) <= ci_high


def test_always_flat_and_persistence_baselines():
    records = _synthetic_settled(n=60)
    flat = AlwaysFlatBaseline()
    band, probs = flat.predict("X", "2026-09-01")
    assert band == "flat" and probs == {"up": 0.0, "flat": 1.0, "down": 0.0}

    persistence = persistence_baseline(records, flat_threshold=0.003)
    assert persistence, "persistence baseline should produce predictions for follow-on dates"
    for (ticker, trade_date), (band, probs) in persistence.items():
        assert band in ("up", "flat", "down")
        assert probs[band] == 1.0
        earlier = [r for r in records if r.ticker == ticker and r.trade_date < trade_date]
        assert earlier, "prediction must be grounded in a prior settled record"
