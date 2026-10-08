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

Stale-generation reclaim (ALG-3308): after the API container is recreated,
leases in the shared state volume still name holders in the dead container's
PID namespace — liveness can never be confirmed from the new one, and every
start used to be denied (the demo then ran with zero engines, silently). The
supervisor therefore reclaims an unknown holder's lease when BOTH its age and
the account's heartbeat silence exceed ``stale_after`` (default 10 min): fresh
heartbeat evidence always wins (a rolling overlap stays denied), and every
eviction preserves the old lease in a ``*.evicted`` sidecar.

Lifecycle: ``starting -> reconciling -> ready -> stopped / exited / denied``
(plus ``stale`` when heartbeats stop).

Isolation (ALG-3259): every worker is launched through ``sandbox`` with an
environment scoped to its own account (``scoped_env``). The sandbox applies
the memory rlimit and nice level, and drops to a non-root UID when one is
configured (``Isolation.from_env``: ``ALGOBOTS_WORKER_UID``). The supervisor
then hands that UID the worker state it must write. A worker that the sandbox
refuses exits ``EXIT_SANDBOX`` and is reported ``exited``. Management stays
in-process (API lifespan); ``/demo/api/workers`` only reads ``status``.

Stdlib only: the API imports this without importing Nautilus.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from algobots.engine.workers.lease import (
    EXIT_DENIED,
    STALE_LEASE_S,
    Lease,
    LeaseDenied,
)
from algobots.engine.workers.sandbox import scoped_env

__all__ = ["Isolation", "LeaseDenied", "Supervisor", "WorkerStatus"]

logger = logging.getLogger("algobots.engine.workers")

HEARTBEAT_STALE_S = 60.0  # > 2 polls missed at the 15 s default
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


@dataclass
class Isolation:
    """What the sandbox enforces per worker; ``uid=None`` keeps the supervisor's UID."""

    uid: int | None = None
    gid: int | None = None
    mem_mb: int = 4096  # RLIMIT_AS: Nautilus maps ~2.4 GB virtual for ~350 MB RSS
    nice: int = 10
    netns: bool = True  # try a private netns; falls back to "asserted" without CAP_SYS_ADMIN
    forbid: tuple[str, ...] | None = None  # None: sandbox.FORBIDDEN_PATHS

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> Isolation:
        env = os.environ if environ is None else environ
        uid = env.get("ALGOBOTS_WORKER_UID")
        gid = env.get("ALGOBOTS_WORKER_GID")
        return cls(
            uid=int(uid) if uid else None,
            gid=int(gid) if gid else None,
            mem_mb=int(env.get("ALGOBOTS_WORKER_MEM_MB", "4096")),
        )

    def argv(self, account: str, state_dir: Path) -> list[str]:
        a = [sys.executable, "-m", "algobots.engine.workers.sandbox", "--account", account]
        a += ["--state-dir", str(state_dir), "--mem-mb", str(self.mem_mb)]
        a += ["--nice", str(self.nice)] + (["--netns"] if self.netns else [])
        for p in self.forbid or ():
            a += ["--forbid", p]
        if self.uid is not None:
            gid = self.gid if self.gid is not None else self.uid
            a += ["--uid", str(self.uid), "--gid", str(gid)]
        return [*a, "--"]


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
    uid: int | None = None  # the worker process's real UID, from /proc


def proc_stats(pid: int) -> tuple[float | None, float | None] | None:
    """(RSS MB, CPU seconds) from /proc; None if the process is gone.

    An unreadable stat file (e.g. hidepid) returns ``(None, None)``: the worker
    is alive but this process may not measure it, so ``status()`` keeps
    reporting from the heartbeat instead of raising or waiting for exit.
    """
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (FileNotFoundError, ProcessLookupError, IndexError):
        return None
    except PermissionError:
        return (None, None)
    if fields[0] == "Z":  # zombie: exited, not yet reaped
        return None
    utime, stime, rss_pages = int(fields[11]), int(fields[12]), int(fields[21])
    return round(rss_pages * _PAGE / 2**20, 1), round((utime + stime) / _CLK_TCK, 2)


def proc_uid(pid: int) -> int | None:
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("Uid:"):
                return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        pass
    return None


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
        isolation: Isolation | None = None,
        stale_after: float = STALE_LEASE_S,
        reclaim_stale_leases: bool = True,
    ) -> None:
        self.accounts = list(accounts)
        self.state_dir = Path(state_dir)
        self.poll = poll
        # Overridable for tests; the account key and poll are appended per worker.
        self.command = command or [sys.executable, "-m", "algobots.engine.workers.paper"]
        self.env = env  # extras added after the per-account scoping
        self.isolation = isolation or Isolation.from_env()
        self.stale_after = stale_after
        self.reclaim_stale_leases = reclaim_stale_leases
        self.procs: dict[str, subprocess.Popen] = {}
        self.spawned_at: dict[str, float] = {}
        self.stopped: set[str] = set()
        self.denied: dict[str, str] = {}  # account -> why start was refused
        self.reclaimed: dict[str, str] = {}  # account -> why a stale lease was evicted (ALG-3308)
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

    def add(self, account: str) -> None:
        """Supervise one more key (a template deployment id, ALG-3281); idempotent."""
        with self._lock:
            if account not in self.leases:
                self.accounts.append(account)
                self.leases[account] = Lease(self.state_dir, account)

    def _start_one(self, acct: str) -> None:
        p = self.procs.get(acct)
        if p is not None and p.poll() is None:
            raise LeaseDenied(acct, f"worker already running under this supervisor (pid {p.pid})")
        lease = self.leases[acct]
        with lease.locked():  # check -> spawn -> record child, atomically w.r.t. other owners
            try:
                holder = lease.check(
                    now=time.time(),
                    stale_after=self.stale_after,
                    reclaim_stale=self.reclaim_stale_leases,
                )
            except LeaseDenied as e:
                self.denied[acct] = e.reason
                self.procs.pop(acct, None)
                raise
            if holder.lease is not None and holder.reason.startswith("reclaimed stale lease:"):
                self.reclaimed[acct] = holder.reason
                logger.warning("reclaimed stale lease for %s: %s", acct, holder.reason)
            hb = self.state_dir / "workers" / f"{acct}.json"
            hb.unlink(missing_ok=True)  # never report a previous run's heartbeat
            log = self.state_dir / "workers" / f"{acct}.log"
            log.parent.mkdir(parents=True, exist_ok=True)
            self._hand_over(lease)
            self.procs[acct] = proc = subprocess.Popen(
                [
                    *self.isolation.argv(acct, self.state_dir),
                    *self.command,
                    *("--account", acct, "--poll", str(self.poll)),
                ],
                stdout=log.open("ab"),
                stderr=subprocess.STDOUT,
                env={**scoped_env(acct, dict(os.environ)), **(self.env or {})},
                start_new_session=True,  # a signal to the API never cascades
            )
            lease.write(proc.pid)
            self._hand_over(lease)
        self.spawned_at[acct] = time.time()
        self.stopped.discard(acct)
        self.denied.pop(acct, None)

    def _hand_over(self, lease: Lease) -> None:
        """Let the worker UID write its heartbeat and release its own lease."""
        uid = self.isolation.uid
        if uid is None:
            return
        gid = self.isolation.gid if self.isolation.gid is not None else uid
        lock = lease.path.with_suffix(".lock")
        lock.touch()
        for p in (self.state_dir / "workers", lease.path.parent, lock, lease.path):
            if p.exists():
                os.chown(p, uid, gid)

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
        st.uid = proc_uid(p.pid)
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
