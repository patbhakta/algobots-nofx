"""Supervisor for the per-account paper workers (ALG-3255/ALG-3258, A06 slices 1-2).

Starts one OS process per demo account, stops them, and reports a
``WorkerStatus`` for each from two independent sources: the process table
(``/proc``: alive, RSS, CPU) and the worker's own heartbeat file (ready,
last heartbeat, orders). A worker that dies is reported ``exited`` with its
exit code and is NOT restarted, so a kill is visible; the others keep
trading because nothing is shared between processes but the read-only feed.

Ownership is durable (``lease``): ``start`` takes the account's lease for the
child PID under the lease lock, and raises ``LeaseDenied`` (state ``denied``)
if another live process, e.g. a second API process or an orphan from a
previous run, holds it or its owner's liveness can't be confirmed. A
restarted worker reports ``reconciling`` and is entry-frozen until its
heartbeat says ``ready`` (reconciled from the durable ledger).

Lifecycle: ``starting -> reconciling -> ready -> stopped / exited / denied``
(plus ``stale`` when heartbeats stop).

Stdlib only: the API imports this without importing Nautilus.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from algobots.engine.workers.lease import EXIT_DENIED, Lease, LeaseDenied

__all__ = ["LeaseDenied", "Supervisor", "WorkerStatus"]

HEARTBEAT_STALE_S = 60.0  # > 2 polls missed at the 15 s default
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


@dataclass
class WorkerStatus:
    account: str
    state: str  # not_started / starting / reconciling / ready / stale / exited / stopped / denied
    pid: int | None = None
    exit_code: int | None = None
    rss_mb: float | None = None
    cpu_s: float | None = None  # user + system CPU seconds since start
    started_at: float | None = None
    startup_s: float | None = None  # spawn -> first heartbeat
    last_heartbeat: float | None = None
    trader_id: str | None = None
    account_id: str | None = None
    order_id_tag: str | None = None
    intervals: int | None = None  # feed intervals processed so far
    orders_submitted: int | None = None
    orders_filled: int | None = None
    open_positions: int | None = None
    reconciled: bool = False  # rebuilt from durable state; entries allowed
    orders_restored: int | None = None  # replayed into the venue during reconcile
    orders_rejected_frozen: int | None = None  # entries refused while entry-frozen
    denied_reason: str | None = None
    lease_pid: int | None = None  # current lease holder per the lease file


def proc_stats(pid: int) -> tuple[float, float] | None:
    """(RSS MB, CPU seconds) from /proc, or None if the process is gone."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return None
    if fields[0] == "Z":  # zombie: exited, not yet reaped
        return None
    utime, stime, rss_pages = int(fields[11]), int(fields[12]), int(fields[21])
    return round(rss_pages * _PAGE / 2**20, 1), round((utime + stime) / _CLK_TCK, 2)


def read_heartbeat(state_dir: Path, account: str) -> dict | None:
    try:
        return json.loads((state_dir / "workers" / f"{account}.json").read_text())
    except (FileNotFoundError, ValueError):
        return None


class Supervisor:
    def __init__(
        self,
        accounts: list[str],
        state_dir: Path,
        *,
        poll: float = 15.0,
        command: list[str] | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.accounts = list(accounts)
        self.state_dir = Path(state_dir)
        self.poll = poll
        # Overridable for tests; the account key and poll are appended per worker.
        self.command = command or [sys.executable, "-m", "algobots.engine.workers.paper"]
        self.env = env
        self.procs: dict[str, subprocess.Popen] = {}
        self.spawned_at: dict[str, float] = {}
        self.stopped: set[str] = set()
        self.denied: dict[str, str] = {}  # account -> why start was refused
        self.leases = {a: Lease(self.state_dir, a) for a in self.accounts}
        self._lock = threading.Lock()

    def start(self, account: str | None = None) -> None:
        """Start the account's worker (default: every account), one owner per account.

        Accounts that can't be started raise ``LeaseDenied`` after the others
        have started; with several denials, the first is raised and carries
        them all in ``.denials``. A denial for a worker this supervisor
        already runs leaves that worker untouched.
        """
        denials: list[LeaseDenied] = []
        with self._lock:
            for acct in [account] if account else self.accounts:
                try:
                    self._start_one(acct)
                except LeaseDenied as e:
                    denials.append(e)
        if denials:
            denials[0].denials = denials
            raise denials[0]

    def _start_one(self, acct: str) -> None:
        p = self.procs.get(acct)
        if p is not None and p.poll() is None:
            raise LeaseDenied(acct, f"worker already running under this supervisor (pid {p.pid})")
        lease = self.leases[acct]
        with lease.locked():  # check -> spawn -> record child, atomically w.r.t. other owners
            try:
                lease.check()
            except LeaseDenied as e:
                self.denied[acct] = e.reason
                self.procs.pop(acct, None)
                raise
            hb = self.state_dir / "workers" / f"{acct}.json"
            hb.unlink(missing_ok=True)  # never report a previous run's heartbeat
            log = self.state_dir / "workers" / f"{acct}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            self.procs[acct] = proc = subprocess.Popen(
                [*self.command, "--account", acct, "--poll", str(self.poll)],
                stdout=log.open("ab"),
                stderr=subprocess.STDOUT,
                env={**os.environ, **(self.env or {})},
                start_new_session=True,  # a signal to the API never cascades
            )
            lease.write(proc.pid)
        self.spawned_at[acct] = time.time()
        self.stopped.discard(acct)
        self.denied.pop(acct, None)

    def stop(self, account: str | None = None, timeout: float = 10.0) -> None:
        with self._lock:
            targets = [account] if account else list(self.procs)
            for acct in targets:
                p = self.procs.get(acct)
                if p is None:
                    continue
                self.stopped.add(acct)
                if p.poll() is None:
                    p.terminate()
            for acct in targets:
                p = self.procs.get(acct)
                if p is None:
                    continue
                try:
                    p.wait(timeout)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait()
                self.leases[acct].release(p.pid)  # termination confirmed: hand the account back

    def status(self, account: str, now: float | None = None) -> WorkerStatus:
        now = time.time() if now is None else now
        st = WorkerStatus(account=account, state="not_started")
        lease = self.leases[account].read() if account in self.leases else None
        st.lease_pid = lease.get("pid") if lease else None
        if account in self.denied:
            st.state, st.denied_reason = "denied", self.denied[account]
            return st
        p = self.procs.get(account)
        if p is None:
            return st
        st.pid, st.started_at = p.pid, self.spawned_at.get(account)
        hb = read_heartbeat(self.state_dir, account)
        if hb and hb.get("pid") == p.pid:
            st.last_heartbeat = hb.get("last_heartbeat")
            st.trader_id, st.account_id = hb.get("trader_id"), hb.get("account_id")
            st.order_id_tag = hb.get("order_id_tag")
            st.intervals = hb.get("intervals")
            st.orders_submitted, st.orders_filled = (
                hb.get("orders_submitted"),
                hb.get("orders_filled"),
            )
            st.open_positions = hb.get("open_positions")
            st.reconciled = bool(hb.get("reconciled"))
            st.orders_restored = hb.get("orders_restored")
            st.orders_rejected_frozen = hb.get("orders_rejected_frozen")
            if st.started_at and hb.get("ready_at"):
                st.startup_s = round(hb["ready_at"] - st.started_at, 2)
        code = p.poll()
        stats = None if code is not None else proc_stats(p.pid)
        if code is not None or stats is None:
            st.exit_code = code if code is not None else p.wait()
            if st.exit_code == EXIT_DENIED:  # lost an ownership race inside the worker
                st.state = "denied"
                st.denied_reason = f"worker could not take the lease (held by pid {st.lease_pid})"
            else:
                st.state = "stopped" if account in self.stopped else "exited"
            return st
        st.rss_mb, st.cpu_s = stats
        if st.last_heartbeat is None:
            st.state = "starting"
        elif now - st.last_heartbeat > HEARTBEAT_STALE_S:
            st.state = "stale"
        elif not st.reconciled:
            st.state = "reconciling"  # entry-frozen
        else:
            st.state = "ready"
        return st

    def ready(self) -> bool:
        return all(self.status(a).state == "ready" for a in self.accounts)

    def snapshot(self) -> list[dict]:
        return [asdict(self.status(a)) for a in self.accounts]
