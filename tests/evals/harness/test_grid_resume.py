import json
from datetime import date

import pytest

from algobots.evals.harness import DecisionRecord
from algobots.evals.harness.grid import (
    CorruptStateError,
    GridCell,
    SkipCell,
    load_checkpoint,
    plan_grid,
    run_grid,
    trading_dates_back_from,
)


def _evaluate_factory(fail_on=None):
    calls = {"n": 0}

    def evaluate(ticker, trade_date):
        calls["n"] += 1
        if fail_on is not None and calls["n"] in fail_on:
            raise RuntimeError(f"simulated interruption on call {calls['n']}")
        return DecisionRecord(
            decision_id=f"{ticker}-{trade_date}",
            ticker=ticker,
            trade_date=trade_date,
            band="up",
            probabilities={"up": 0.6, "flat": 0.2, "down": 0.2},
            horizon_days=1,
        )

    return evaluate, calls


def test_plan_only_spends_nothing(tmp_path):
    cells = plan_grid(["AAPL", "MSFT"], ["2026-09-15", "2026-09-16"])
    evaluate, calls = _evaluate_factory()
    _, stats = run_grid(cells, evaluate, checkpoint_path=tmp_path / "cp.jsonl", plan_only=True)
    assert calls["n"] == 0
    assert stats.executed == 4 and stats.errors == 0 and stats.skipped == 0


def test_resume_after_interruption(tmp_path):
    """Q&A gate: runs resume after interruption; completed cells are never re-executed."""
    cells = plan_grid(["AAPL", "MSFT"], ["2026-09-15", "2026-09-16", "2026-09-17"])
    cp = tmp_path / "cp.jsonl"
    evaluate, calls = _evaluate_factory(fail_on={3})
    records1, stats1 = run_grid(cells, evaluate, checkpoint_path=cp, max_errors=1)
    assert stats1.executed == 2 and stats1.errors == 1
    assert calls["n"] == 3

    evaluate2, calls2 = _evaluate_factory()
    records2, stats2 = run_grid(cells, evaluate2, checkpoint_path=cp)
    assert stats2.skipped == 2, "cells already ok in the checkpoint must be skipped"
    assert stats2.executed == 4, "errored and unattempted cells must be retried on resume"
    assert calls2["n"] == 4

    clean_evaluate, _ = _evaluate_factory()
    records_clean, _ = run_grid(cells, clean_evaluate)
    assert {r.decision_id for r in records2 + records1} == {r.decision_id for r in records_clean}


def test_truncated_checkpoint_tolerated(tmp_path):
    cp = tmp_path / "cp.jsonl"
    ok = json.dumps({"key": "AAPL@2026-09-15", "status": "ok"})
    torn = '{"key": "AAPL@2026-09-16", "sta'
    cp.write_text(ok + "\n" + torn, encoding="utf-8")
    done, lines = load_checkpoint(cp)
    assert done == {"AAPL@2026-09-15"}
    assert len(lines) == 1


def test_torn_tail_truncated_and_cell_reexecutes(tmp_path):
    """Line B port: torn final line is dropped, file truncated, cell re-executes."""
    cp = tmp_path / "cp.jsonl"
    ok = json.dumps({"key": "AAPL@2026-09-15", "status": "ok"})
    torn = '{"key": "AAPL@2026-09-16", "sta'
    cp.write_text(ok + "\n" + torn, encoding="utf-8")
    size_before = cp.stat().st_size
    done, _ = load_checkpoint(cp)
    assert done == {"AAPL@2026-09-15"}
    assert cp.stat().st_size < size_before, "torn tail must be physically truncated"
    assert cp.read_text(encoding="utf-8").count("\n") == 1

    cells = plan_grid(["AAPL"], ["2026-09-15", "2026-09-16"])
    evaluate, calls = _evaluate_factory()
    records, stats = run_grid(cells, evaluate, checkpoint_path=cp)
    assert stats.skipped == 1, "the intact ok cell is not re-executed"
    assert stats.executed == 1, "the torn cell re-executes on a clean tail"
    assert calls["n"] == 1


def test_midfile_corruption_raises_corrupt_state_error(tmp_path):
    """Line B port: corruption with content after it fails loudly, never silently drops evidence."""
    cp = tmp_path / "cp.jsonl"
    cp.write_text(
        json.dumps({"key": "AAPL@2026-09-15", "status": "ok"}) + "\n"
        + '{"key": "AAPL@2026-09-16", "st' + "!!!corrupted!!!" + "\n"
        + json.dumps({"key": "AAPL@2026-09-17", "status": "ok"}) + "\n",
        encoding="utf-8",
    )
    with pytest.raises(CorruptStateError):
        load_checkpoint(cp)


def test_skip_cell_persists_and_never_retries(tmp_path):
    """Line B port: no-data skips are persisted, never retried, never scored."""
    cells = plan_grid(["AAA"], ["2026-01-02", "2026-01-03", "2026-01-05"])
    cp = tmp_path / "cp.jsonl"
    calls: list[tuple[str, str]] = []

    def evaluate(ticker, trade_date):
        calls.append((ticker, trade_date))
        if trade_date == "2026-01-03":
            return SkipCell("missing_bars")
        return DecisionRecord(
            decision_id=f"{ticker}-{trade_date}",
            ticker=ticker,
            trade_date=trade_date,
            band="up",
            probabilities={"up": 0.6, "flat": 0.2, "down": 0.2},
            horizon_days=1,
        )

    records, stats = run_grid(cells, evaluate, checkpoint_path=cp)
    assert stats.executed == 2 and stats.no_data_skipped == 1
    assert stats.skip_keys == ["AAA@2026-01-03"]
    assert len(records) == 2, "skipped cells never enter scoring evidence"
    persisted = [json.loads(line) for line in cp.read_text(encoding="utf-8").splitlines()]
    skip_entries = [e for e in persisted if e.get("kind") == "skip"]
    assert skip_entries == [
        {"key": "AAA@2026-01-03", "kind": "skip", "status": "skip", "reason": "missing_bars"}
    ]

    evaluate2, calls2 = _evaluate_factory()
    records2, stats2 = run_grid(cells, evaluate2, checkpoint_path=cp)
    assert stats2.skipped == 3 and stats2.executed == 0, "a persisted skip is permanent on resume"
    assert calls2["n"] == 0


def test_none_return_is_a_no_data_skip(tmp_path):
    """Line B port: a bare None short-hands SkipCell(reason='no_data')."""
    cells = plan_grid(["BBB"], ["2026-02-02"])
    cp = tmp_path / "cp.jsonl"

    def evaluate(ticker, trade_date):
        return None

    records, stats = run_grid(cells, evaluate, checkpoint_path=cp)
    assert stats.no_data_skipped == 1 and stats.executed == 0
    assert records == []
    entry = json.loads(cp.read_text(encoding="utf-8").strip())
    assert entry["reason"] == "no_data" and entry["status"] == "skip"


def test_line_b_shaped_skip_entries_join_done_set(tmp_path):
    """Line B port: stock-vaults-shaped skip markers (ticker/date) migrate into the done set."""
    cp = tmp_path / "cp.jsonl"
    marker = json.dumps({"kind": "skip", "ticker": "AAA", "date": "2026-01-03", "reason": "no"})
    cp.write_text(marker + "\n", encoding="utf-8")
    done, lines = load_checkpoint(cp)
    assert "AAA@2026-01-03" in done
    assert len(lines) == 1


def test_error_entries_are_history_not_done(tmp_path):
    """Transient-failure vs permanent-skip: error entries retry on resume, skips do not."""
    cp = tmp_path / "cp.jsonl"
    cp.write_text(
        json.dumps({"key": "AAA@2026-01-02", "status": "error", "error": "boom"}) + "\n"
        + json.dumps({"key": "AAA@2026-01-03", "status": "skip", "reason": "no_data"}) + "\n",
        encoding="utf-8",
    )
    done, _ = load_checkpoint(cp)
    assert "AAA@2026-01-03" in done
    assert "AAA@2026-01-02" not in done


def test_trading_dates_helper():
    dates = trading_dates_back_from("2026-09-21", 5)
    assert dates[-1] == "2026-09-21"
    assert len(dates) == 5
    assert all(date.fromisoformat(d).weekday() < 5 for d in dates)
    assert dates == sorted(dates)


def test_cell_key_roundtrip():
    assert GridCell("AAPL", "2026-09-15").key() == "AAPL@2026-09-15"
