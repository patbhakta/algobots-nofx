"""ALG-3258 A06-2: durable per-account ownership (AC2, AC3) and crash -> frozen (AC4)."""

import json
import os
import signal
import subprocess
import sys
import threading
import time

import pytest

from algobots.engine.workers import lease as LS
from algobots.engine.workers.lease import EXIT_DENIED, Lease, LeaseDenied

from .test_supervisor import _supervisor, _wait


@pytest.fixture
def sleeper():
    """An unrelated live process to stand in for another owner."""
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield p
    p.kill()
    p.wait()


def _plant(tmp_path, account: str, **lease) -> Lease:
    ls = Lease(tmp_path, account)
    ls.path.parent.mkdir(parents=True, exist_ok=True)
    ls.path.write_text(json.dumps(lease))
    return ls


def _live_procs(account: str, tmp_path) -> list[int]:
    """PIDs of fake workers for ``account`` under this test's state dir."""
    out = []
    for d in os.listdir("/proc"):
        if not d.isdigit():
            continue
        try:
            cmd = open(f"/proc/{d}/cmdline", "rb").read().split(b"\0")
            env = open(f"/proc/{d}/environ", "rb").read()
            stat = open(f"/proc/{d}/stat").read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if stat[0] == "Z":
            continue
        if account.encode() in cmd and f"STATE={tmp_path}".encode() in env:
            out.append(int(d))
    return out


# --- AC2: two viewers/callers of one account -> exactly one worker -------------------


def test_two_supervisors_one_account_exactly_one_worker(tmp_path):
    a, b = _supervisor(tmp_path), _supervisor(tmp_path)  # e.g. two API processes
    errors: list[LeaseDenied] = []

    def go(sup):
        try:
            sup.start("laya")
        except LeaseDenied as e:
            errors.append(e)

    ts = [threading.Thread(target=go, args=(s,)) for s in (a, b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    try:
        assert len(errors) == 1 and "live pid" in errors[0].reason
        winner, loser = (a, b) if "laya" in a.procs else (b, a)
        assert _wait(lambda: winner.status("laya").state == "ready")
        assert len(_live_procs("laya", tmp_path)) == 1
        st = loser.status("laya")
        assert st.state == "denied" and st.denied_reason == errors[0].reason
        assert st.lease_pid == winner.status("laya").pid
    finally:
        a.stop()
        b.stop()


def test_second_start_on_same_supervisor_is_denied_and_keeps_worker(tmp_path):
    sup = _supervisor(tmp_path)
    sup.start("jev")
    try:
        assert _wait(lambda: sup.status("jev").state == "ready")
        pid = sup.status("jev").pid
        with pytest.raises(LeaseDenied, match="already running"):
            sup.start("jev")
        assert sup.status("jev").state == "ready" and sup.status("jev").pid == pid
        assert _live_procs("jev", tmp_path) == [pid]
    finally:
        sup.stop()


def test_start_all_starts_free_accounts_and_reports_denied_ones(tmp_path, sleeper):
    _plant(tmp_path, "coin", **LS.identity(sleeper.pid))
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied) as ei:
        sup.start()
    try:
        assert [e.account for e in ei.value.denials] == ["coin"]
        assert _wait(lambda: all(sup.status(a).state == "ready" for a in ("laya", "jev")))
        assert sup.status("coin").state == "denied"
        assert sup.snapshot()[2]["denied_reason"].startswith(
            f"lease held by live pid {sleeper.pid}"
        )
    finally:
        sup.stop()


# --- AC3: lease held by a live or unknown PID -> denied; takeover only when confirmed dead


def test_live_pid_lease_denies_start(tmp_path, sleeper):
    _plant(tmp_path, "laya", **LS.identity(sleeper.pid))
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied, match="live pid"):
        sup.start("laya")
    assert "laya" not in sup.procs and _live_procs("laya", tmp_path) == []
    with pytest.raises(LeaseDenied, match="stop it first"):
        Lease(tmp_path, "laya").force_release()  # never yanks a live owner


@pytest.mark.parametrize(
    "lease",
    [
        {"host": "other-host"},  # written on another host
        {"pidns": "pid:[1]"},  # another PID namespace (e.g. an old container)
        None,  # corrupt lease file
    ],
)
def test_unknown_owner_denies_start_until_force_release(tmp_path, sleeper, lease):
    ls = Lease(tmp_path, "laya")
    if lease is None:
        ls.path.parent.mkdir(parents=True, exist_ok=True)
        ls.path.write_text("{not json")
    else:
        _plant(tmp_path, "laya", **{**LS.identity(sleeper.pid), **lease})
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied) as ei:
        sup.start("laya")
    assert ls.holder().status == "unknown"
    assert (
        sup.status("laya").state == "denied" and sup.status("laya").denied_reason == ei.value.reason
    )

    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "algobots.engine.workers.lease",
            "force-release",
            "--account",
            "laya",
            "--state-dir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=True,
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert "released" in out.stdout and "unknown" in out.stdout
    sup.start("laya")
    try:
        assert _wait(lambda: sup.status("laya").state == "ready")
        assert sup.status("laya").denied_reason is None
    finally:
        sup.stop()


def test_dead_or_reused_pid_is_taken_over(tmp_path, sleeper):
    dead = subprocess.Popen([sys.executable, "-c", "pass"])
    dead.wait()
    _plant(tmp_path, "laya", **{**LS.identity(sleeper.pid), "pid": dead.pid, "start_time": 1})
    reused = {**LS.identity(sleeper.pid)}
    reused["start_time"] -= 1  # same PID, different process
    _plant(tmp_path, "jev", **reused)
    for acct in ("laya", "jev"):
        assert Lease(tmp_path, acct).holder().status == "dead"
    sup = _supervisor(tmp_path)
    sup.start("laya")
    sup.start("jev")
    try:
        assert _wait(lambda: sup.status("laya").state == sup.status("jev").state == "ready")
        for acct in ("laya", "jev"):
            assert Lease(tmp_path, acct).read()["pid"] == sup.status(acct).pid
    finally:
        sup.stop()


def test_worker_that_loses_the_race_exits_denied(tmp_path, sleeper):
    """The worker re-checks the lease itself; a loser exits EXIT_DENIED -> state denied."""
    _plant(tmp_path, "laya", **LS.identity(sleeper.pid))
    sup = _supervisor(tmp_path)
    ls = Lease(tmp_path, "laya")
    # Simulate the race: bypass the supervisor's check, then run the worker's acquire.
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; from pathlib import Path;"
            "from algobots.engine.workers.lease import Lease, LeaseDenied, EXIT_DENIED\n"
            f"try: Lease(Path({str(tmp_path)!r}), 'laya').acquire()\n"
            "except LeaseDenied: sys.exit(EXIT_DENIED)",
        ],
        env={**os.environ, "PYTHONPATH": os.pathsep.join(sys.path)},
    )
    assert child.returncode == EXIT_DENIED and ls.read()["pid"] == sleeper.pid
    sup.procs["laya"] = subprocess.Popen(
        [sys.executable, "-c", f"import sys; sys.exit({EXIT_DENIED})"]
    )
    sup.procs["laya"].wait()
    st = sup.status("laya")
    assert st.state == "denied" and f"pid {sleeper.pid}" in st.denied_reason


# --- ALG-3308: stale leases from a dead container generation --------------------


def _plant_from_old_container(
    tmp_path, account: str, *, acquired_ago: float, heartbeat_ago: float | None
):
    """Lease + heartbeat as a DEAD container generation left them: holder in
    an unprobable PID namespace, acquisition and heartbeat from that era."""
    now = time.time()
    _plant(
        tmp_path,
        account,
        **{**LS.identity(os.getpid()), "pidns": "pid:[1]", "acquired_at": now - acquired_ago},
    )
    hb = tmp_path / "workers" / f"{account}.json"
    hb.parent.mkdir(parents=True, exist_ok=True)
    if heartbeat_ago is not None:
        hb.write_text(json.dumps({"pid": 1, "last_heartbeat": now - heartbeat_ago}))


def test_stale_generation_lease_is_reclaimed_at_start(tmp_path):
    """The incident replay: container recreated >10 min after death. The new
    supervisor cannot probe the old namespace, but lease age + heartbeat
    silence prove the generation is gone -> evict, start, ready."""
    _plant_from_old_container(
        tmp_path, "laya", acquired_ago=900, heartbeat_ago=900
    )
    sup = _supervisor(tmp_path)
    ls = Lease(tmp_path, "laya")
    sup.start("laya")
    try:
        assert _wait(lambda: sup.status("laya").state == "ready")
        assert sup.status("laya").denied_reason is None
        assert "laya" in sup.reclaimed and "generation is gone" in sup.reclaimed["laya"]
        assert ls.read()["pid"] == sup.status("laya").pid
        evicted = list(ls.path.parent.glob("*.evicted"))
        assert len(evicted) == 1, "the evicted lease is preserved for forensics"
        record = json.loads(evicted[0].read_text())
        assert record["evicted_lease"]["pidns"] == "pid:[1]"
        assert "generation is gone" in record["reason"]
    finally:
        sup.stop()


def test_missing_heartbeat_old_lease_is_also_reclaimable(tmp_path):
    """Old lease, no heartbeat file at all: the holder never got ready or the
    generation died before writing one — either way it has been silent."""
    _plant_from_old_container(tmp_path, "jev", acquired_ago=1200, heartbeat_ago=None)
    sup = _supervisor(tmp_path)
    sup.start("jev")
    try:
        assert _wait(lambda: sup.status("jev").state == "ready")
        assert "no heartbeat on record" in sup.reclaimed["jev"]
    finally:
        sup.stop()


def test_fresh_unknown_lease_still_denied(tmp_path):
    """A young lease in another namespace may be a concurrently-starting
    generation (fast recreate, slow reconcile): denied, not reclaimed."""
    _plant_from_old_container(tmp_path, "coin", acquired_ago=60, heartbeat_ago=60)
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied):
        sup.start("coin")
    assert sup.status("coin").state == "denied" and "laya" not in sup.reclaimed
    assert sup.reclaimed == {} and not list(Lease(tmp_path, "coin").path.parent.glob("*.evicted"))
    sup.stop()


def test_old_lease_with_fresh_heartbeat_still_denied(tmp_path):
    """Rolling overlap: the other container's worker is alive and heartbeating
    (long-running, lease acquired long ago) — fresh evidence wins, no reclaim."""
    _plant_from_old_container(tmp_path, "laya", acquired_ago=3600, heartbeat_ago=5)
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied):
        sup.start("laya")
    assert sup.status("laya").state == "denied" and sup.reclaimed == {}
    sup.stop()


def test_timestampless_lease_is_never_auto_reclaimed(tmp_path, sleeper):
    """Planted/corrupt leases carry no acquired_at: no proof, no eviction —
    the operator force-release path stays the only way (A06 behavior)."""
    _plant(tmp_path, "laya", **{**LS.identity(sleeper.pid), "pidns": "pid:[1]"})
    assert Lease(tmp_path, "laya").read().get("acquired_at") is None
    sup = _supervisor(tmp_path)
    with pytest.raises(LeaseDenied):
        sup.start("laya")
    assert sup.reclaimed == {} and Lease(tmp_path, "laya").path.exists()
    sup.stop()


# --- AC4: crash -> that account is frozen until restart + reconcile; others keep running


def test_crash_freezes_only_that_account_until_reconciled(tmp_path):
    sup = _supervisor(tmp_path)
    sup.start()
    try:
        assert _wait(sup.ready)
        dead_pid = sup.status("coin").pid
        os.kill(dead_pid, signal.SIGKILL)
        assert _wait(lambda: sup.status("coin").state == "exited")
        assert Lease(tmp_path, "coin").holder().status == "dead"  # left behind, confirmed dead
        before = {a: sup.status(a).orders_submitted for a in ("laya", "jev")}
        assert _wait(lambda: all(sup.status(a).orders_submitted > before[a] for a in before))

        sup.env["RECONCILE_S"] = "1.0"  # the restarted worker takes a while to reconcile
        sup.start("coin")
        assert _wait(lambda: sup.status("coin").state == "reconciling")
        st = sup.status("coin")
        assert st.pid != dead_pid and not st.reconciled and st.orders_submitted == 0
        assert sup.status("laya").state == "ready" and not sup.ready()
        assert _wait(lambda: sup.status("coin").state == "ready")
        assert sup.status("coin").reconciled and sup.ready()
    finally:
        sup.stop()
