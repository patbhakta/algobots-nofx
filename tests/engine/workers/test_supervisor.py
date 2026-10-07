"""ALG-3255/3258 supervisor: N accounts -> N processes; one kill is isolated and reported;
one owner per account across supervisors; a restart is entry-frozen until reconciled."""

import os
import signal
import sys
import textwrap
import time

from fastapi.testclient import TestClient

from algobots.engine.workers.lease import Lease
from algobots.engine.workers.supervisor import Supervisor, proc_stats

FAKE_WORKER = textwrap.dedent(
    """
    import argparse, json, os, signal, sys, time
    from pathlib import Path
    ap = argparse.ArgumentParser()
    ap.add_argument("--account"); ap.add_argument("--poll", type=float)
    a = ap.parse_args()
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    out = Path(os.environ["STATE"]) / "workers" / f"{a.account}.json"
    t0, n = time.time(), 0
    frozen_until = t0 + float(os.environ.get("RECONCILE_S", "0"))
    while True:
        ok = time.time() >= frozen_until
        n += ok  # entries only once reconciled
        out.write_text(json.dumps({
            "pid": os.getpid(), "last_heartbeat": time.time(), "ready_at": t0,
            "reconciled": ok, "phase": "ready" if ok else "reconciling",
            "trader_id": f"PAPER-{a.account.upper()}",
            "account_id": f"PAPER_{a.account.upper()}-001",
            "order_id_tag": a.account.upper(), "orders_submitted": n, "orders_filled": n,
            "open_positions": n,
        }))
        time.sleep(a.poll)
    """
)


def _wait(pred, timeout=10.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.05)
    return False


def _supervisor(tmp_path, **env) -> Supervisor:
    script = tmp_path / "fake_worker.py"
    script.write_text(FAKE_WORKER)
    return Supervisor(
        ["laya", "jev", "coin"],
        tmp_path,
        poll=0.1,
        command=[sys.executable, str(script)],
        env={"STATE": str(tmp_path), **env},
    )


def test_n_accounts_n_processes_kill_one_others_keep_running(tmp_path):
    sup = _supervisor(tmp_path)
    assert [sup.status(a).state for a in sup.accounts] == ["not_started"] * 3
    sup.start()
    try:
        assert _wait(sup.ready)
        snap = {s["account"]: s for s in sup.snapshot()}
        pids = {s["pid"] for s in snap.values()}
        assert len(pids) == 3 and os.getpid() not in pids
        assert len({s["trader_id"] for s in snap.values()}) == 3
        assert len({s["account_id"] for s in snap.values()}) == 3
        for s in snap.values():
            assert s["rss_mb"] > 0 and s["cpu_s"] is not None and s["startup_s"] >= 0

        os.kill(snap["jev"]["pid"], signal.SIGKILL)
        assert _wait(lambda: sup.status("jev").state == "exited")
        dead = sup.status("jev")
        assert dead.exit_code == -signal.SIGKILL and dead.rss_mb is None
        # survivors keep heartbeating after the kill
        killed_at = time.time()
        assert _wait(
            lambda: all(
                sup.status(a).state == "ready" and sup.status(a).last_heartbeat > killed_at
                for a in ("laya", "coin")
            )
        )
        assert not sup.ready()

        sup.start("jev")  # explicit restart, new process
        assert _wait(lambda: sup.status("jev").state == "ready")
        assert sup.status("jev").pid != snap["jev"]["pid"]
    finally:
        sup.stop()
    assert {s["state"] for s in sup.snapshot()} == {"stopped"}
    assert not any(Lease(tmp_path, a).path.exists() for a in sup.accounts)  # released on stop


def test_stale_heartbeat_is_reported(tmp_path):
    sup = _supervisor(tmp_path)
    sup.start("coin")
    try:
        assert _wait(lambda: sup.status("coin").state == "ready")
        assert sup.status("coin", now=time.time() + 3600).state == "stale"
    finally:
        sup.stop()


def test_proc_stats_for_self_and_missing_pid():
    rss, cpu = proc_stats(os.getpid())
    assert rss > 0 and cpu >= 0
    assert proc_stats(2**22 + 12345) is None


def test_workers_endpoint_reports_not_started_when_disabled(client: TestClient):
    body = client.get("/demo/api/workers").json()
    assert body["enabled"] is False and body["ready"] is False
    assert [w["account"] for w in body["workers"]] == ["laya", "jev", "coin"]
    assert {w["state"] for w in body["workers"]} == {"not_started"}
