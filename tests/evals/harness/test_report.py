import json

import pytest

from algobots.evals.harness import (
    DecisionRecord,
    MoneyGateError,
    RandomBaseline,
    render_json,
    render_markdown,
    summarize,
)
from algobots.evals.harness.baselines import baseline_summaries


def _settled_records(n=30):
    baseline = RandomBaseline(seed=5)
    records = []
    for i in range(n):
        band, probs = baseline.predict("X", "2026-09-01")
        realized = {"up": 0.05, "flat": 0.0, "down": -0.05}[band]
        r = DecisionRecord(
            decision_id=f"r-{i}",
            ticker="X",
            trade_date="2026-09-01",
            band=band,
            probabilities=probs,
            horizon_days=1,
            model_name="jev",
            model_revision="jev-latest@pin",
            question_set_revision="qs-1",
            preregistered_at="2026-01-01T00:00:00+00:00",
        )
        r.settle(realized_return=realized, benchmark_return=0.0)
        records.append(r)
    return records


def test_report_renders_per_band_with_intervals():
    records = _settled_records()
    summary = summarize(records)
    md = render_markdown(summary, records, title="S2.2 gate check")
    for band in ("up", "flat", "down"):
        assert f"| {band} |" in md
    assert "Wilson 95% CI" in md
    assert "[" in md and "%" in md
    assert "Chance level" in md and "Baseline" in md
    payload = json.loads(render_json(summary, records))
    assert payload["summary"]["overall"]["count"] == n_expected(records)
    assert payload["money_gate"]["preregistered"] is True


def n_expected(records):
    return sum(1 for r in records if r.settled)


def test_report_requires_baselines_for_honesty():
    records = _settled_records(6)
    summary = summarize(records)
    md = render_markdown(summary, records)
    assert "not evidence" in md
    with_baseline = baseline_summaries({"random-seed-5": _settled_records(6)})
    md2 = render_markdown(summary, records, baseline_summaries=with_baseline)
    assert "random-seed-5" in md2


def test_money_gate_blocks_unpreregistered():
    records = _settled_records(4)
    r = DecisionRecord(
        decision_id="late-1",
        ticker="X",
        trade_date="2026-09-02",
        band="up",
        probabilities={"up": 0.6, "flat": 0.2, "down": 0.2},
        horizon_days=1,
    )
    r.settle(realized_return=0.01, benchmark_return=0.0)
    records.append(r)
    summary = summarize(records)
    with pytest.raises(MoneyGateError, match="preregistered"):
        render_markdown(summary, records, gating_money=True)
    with pytest.raises(MoneyGateError, match="preregistered"):
        render_json(summary, records, gating_money=True)
    render_markdown(summary, records, gating_money=False)


def test_report_renders_certification_block_and_verdicts():
    """Line B port: majority-label baseline, verdict line, and per-band vs-baseline column."""
    records = _settled_records()
    summary = summarize(records)
    md = render_markdown(summary, records)
    assert "Majority-label baseline hit-rate:" in md
    assert "Verdict:" in md
    assert "edge demonstrated" in md, "perfect-predictor fixture must certify"
    assert "Vs baseline" in md
    assert "beats-baseline" in md
    payload = json.loads(render_json(summary, records))
    assert payload["summary"]["edge_demonstrated"] is True
    assert payload["summary"]["baseline_hit_rate"] > 0
    assert "base_rates" in payload["summary"]
