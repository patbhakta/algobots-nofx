"""ALG-3270 execution seam: spec-selected client, fills from Nautilus OrderFilled events."""

import json
from decimal import Decimal

import pytest

pytest.importorskip("nautilus_trader")

from algobots.demo import ledger as L  # noqa: E402
from algobots.engine.workers import paper  # noqa: E402
from algobots.engine.workers.execution import (  # noqa: E402
    ENV_VAR,
    AccountWorkerSpec,
    AdapterNotAuthorized,
    reconcile_fills,
    specs,
)
from algobots.engine.workers.paper import PaperWorker  # noqa: E402

from .test_paper import _rows, _worker  # noqa: E402


def test_spec_defaults_to_sandbox_and_rejects_unknown_clients():
    assert AccountWorkerSpec("laya").execution == "sandbox"
    assert AccountWorkerSpec("laya").adapter is None
    assert AccountWorkerSpec("laya", "adapter:interactive_brokers").adapter.venue == (
        "INTERACTIVE_BROKERS"
    )
    for bad in ("adapter:kalshi", "adapter:", "live", "kraken"):
        with pytest.raises(ValueError):
            AccountWorkerSpec("laya", bad)


def test_specs_from_env(monkeypatch):
    accounts = sorted(L.STRATEGIES)
    monkeypatch.delenv(ENV_VAR, raising=False)
    assert {s.execution for s in specs(accounts).values()} == {"sandbox"}
    monkeypatch.setenv(ENV_VAR, "jev=adapter:kraken")
    got = specs(accounts)
    assert got["jev"].execution == "adapter:kraken" and got["laya"].execution == "sandbox"
    with pytest.raises(ValueError):
        specs(accounts, "nobody=sandbox")


def test_worker_default_and_explicit_sandbox_are_the_same_path(tmp_path):
    (tmp_path / "feed.jsonl").write_text("\n".join(_rows(6)) + "\n")
    w = PaperWorker(
        "laya", tmp_path / "feed.jsonl", tmp_path, "2026-10-06", [], AccountWorkerSpec("laya")
    )
    try:
        assert w.reconcile() == 4
        assert w.heartbeat()["execution"] == "sandbox"
    finally:
        w.close()


def test_adapter_spec_is_refused_before_any_engine_exists(tmp_path):
    spec = AccountWorkerSpec("laya", "adapter:interactive_brokers")
    with pytest.raises(AdapterNotAuthorized, match="TWS_USERNAME"):
        PaperWorker("laya", tmp_path / "feed.jsonl", tmp_path, "2026-10-06", [], spec)
    with pytest.raises(ValueError):
        PaperWorker("jev", tmp_path / "f", tmp_path, "2026-10-06", [], AccountWorkerSpec("laya"))


def test_adapter_node_runs_the_same_strategy_without_connecting():
    cfg = paper.node_config(AccountWorkerSpec("coin", "adapter:kraken"))
    assert str(cfg.trader_id) == "PAPER-COIN"
    assert set(cfg.exec_clients) == {"KRAKEN"}
    assert cfg.exec_clients["KRAKEN"].api_key is None  # nothing stored; env at connect
    (strat,) = cfg.strategies
    assert strat.strategy_path == "algobots.engine.workers.paper:DemoPaperStrategy"
    assert strat.config == paper.strategy_kwargs("coin")


def test_fills_come_from_nautilus_events_and_reconcile_to_the_ledger(tmp_path):
    feed = tmp_path / "feed.jsonl"
    feed.write_text("\n".join(_rows(9)) + "\n")
    w = _worker(tmp_path, "laya")
    try:
        w.reconcile()
        fills = w.strategy.fills
        decisions = L.build(L.load_rows(feed)).books["laya"].fills
        assert len(fills) == len(decisions) == w.strategy.filled
        # every fill is a venue event: trade ID, venue account, matched price
        assert all(f["account_id"] == "PAPER_LAYA-001" and f["trade_id"] for f in fills)
        assert {f["px"] for f in fills} == {"0.50"}
        hb = w.heartbeat()
        assert hb["fill_events"] == len(fills) and hb["last_fill"] == fills[-1]

        rec = reconcile_fills(fills, decisions)
        assert rec["matched"] == len(decisions)
        assert rec["missing_in_nautilus"] == rec["extra_in_nautilus"] == []
        for r in rec["rows"]:  # only the whole-contract rounding (< one 50c contract)
            assert Decimal(0) <= Decimal(r["diff_usd"]) < Decimal("0.50")
        json.dumps(rec)  # evidence-serialisable
    finally:
        w.close()
