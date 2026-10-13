"""ALG-3259 declared A06 fixture: four synthetic paper accounts x two strategies, measured."""

import json
import os
import signal
import sys
import time

import pytest

pytest.importorskip("nautilus_trader")

from algobots.engine.workers.fixture import (  # noqa: E402
    FIXTURE_ACCOUNTS,
    STRATEGIES_PER_ACCOUNT,
    FixtureWorker,
    pct,
)
from algobots.engine.workers.supervisor import Isolation, Supervisor  # noqa: E402


def _wait(pred, timeout=60.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_pct_is_nearest_rank():
    assert pct([], 95) is None
    assert pct([3, 1, 2], 50) == 2 and pct(list(range(1, 101)), 95) == 95


def test_fixture_declares_four_accounts_eight_unique_deployments(tmp_path):
    workers = [FixtureWorker(a, tmp_path) for a in FIXTURE_ACCOUNTS]
    try:
        strategies = [str(s.id) for w in workers for s in w.strategies]
        assert len(FIXTURE_ACCOUNTS) == 4 and STRATEGIES_PER_ACCOUNT == 2
        assert len(strategies) == len(set(strategies)) == 8
        assert len({w.ids["trader_id"] for w in workers}) == 4
        assert len({w.ids["venue"] for w in workers}) == 4
    finally:
        for w in workers:
            w.close()


def test_fixture_is_entry_frozen_until_reconciled_and_reports_metrics(tmp_path):
    w = FixtureWorker("syn1", tmp_path, rate=50)
    try:
        w.last_gen = time.time() - 1.0  # one second of quotes is due
        assert w.step() > 0
        assert w.rejected_frozen > 0 and sum(s.submitted for s in w.strategies) == 0
        hb = w.heartbeat()
        assert hb["phase"] == "reconciling" and not hb["reconciled"]

        assert w.reconcile() == 0
        w.last_gen = time.time() - 1.0
        w.step()
        hb = w.heartbeat()
        assert hb["reconciled"] and hb["orders_submitted"] > 0
        assert hb["orders_filled"] == hb["orders_submitted"]
        assert hb["callback_latency_ms"]["p95"] is not None and hb["callback_latency_ms"]["n"] > 0
        assert hb["queue_depth"]["max"] >= 2 and hb["queue_age_ms"]["p95"] >= 0
        fills = (tmp_path / "workers" / "syn1.fills.jsonl").read_text().splitlines()
        assert len(fills) == hb["orders_filled"]
    finally:
        w.close()

    w2 = FixtureWorker("syn1", tmp_path)  # restart: replays the durable fill log
    try:
        assert w2.frozen and w2.reconcile() == len(fills) and not w2.frozen
    finally:
        w2.close()


def test_four_nautilus_accounts_kill_one_others_continue(tmp_path):
    sup = Supervisor(
        list(FIXTURE_ACCOUNTS),
        tmp_path,
        poll=0.5,
        command=[sys.executable, "-m", "algobots.engine.workers.fixture"],
        env={"ALGOBOTS_DEMO_STATE_DIR": str(tmp_path), "PYTHONPATH": os.pathsep.join(sys.path)},
        isolation=Isolation(netns=False, forbid=(str(tmp_path / "absent"),)),
    )
    sup.start()
    try:
        assert _wait(sup.ready, 120), sup.snapshot()
        snap = {s["account"]: s for s in sup.snapshot()}
        assert len({s["pid"] for s in snap.values()}) == 4
        assert len({s["trader_id"] for s in snap.values()}) == 4

        os.kill(snap["syn2"]["pid"], signal.SIGKILL)
        assert _wait(lambda: sup.status("syn2").state == "exited")
        killed_at = time.time()
        assert _wait(
            lambda: all(
                sup.status(a).state == "ready" and sup.status(a).last_heartbeat > killed_at + 1
                for a in ("syn1", "syn3", "syn4")
            )
        )
        hb = json.loads((tmp_path / "workers" / "syn1.json").read_text())
        assert hb["intervals"] > 0 and hb["callback_latency_ms"]["n"] > 0  # still trading

        sup.start("syn2")  # restart: frozen until its own reconcile, then ready
        assert _wait(lambda: sup.status("syn2").state == "ready", 120)
        assert sup.status("syn2").pid != snap["syn2"]["pid"]
    finally:
        sup.stop()
