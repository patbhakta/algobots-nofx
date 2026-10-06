"""Supervisor for the per-account paper workers (ALG-3255, A06 slice 1).

Starts one OS process per demo account, stops them, and reports a
``WorkerStatus`` for each from two independent sources: the process table
(``/proc``: alive, RSS, CPU) and the worker's own heartbeat file (ready,
last heartbeat, orders). A worker that dies is reported ``exited`` with its
exit code and is NOT restarted, so a kill is visible; the others keep
trading because nothing is shared between processes but the read-only feed.

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

HEARTBEAT_STALE_S = 60.0  # > 2 polls missed at the 15 s default
_CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100
_PAGE = os.sysconf("SC_PAGE_SIZE") if hasattr(os, "sysconf") else 4096


@dataclass
class WorkerStatus:
    account: str
    state: str  # starting / ready / stale / exited / stopped / not_started
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
        self.command = command or [sys.executable, "-m", "algobots.workers.paper"]
        self.env = env
        self.procs: dict[str, subprocess.Popen] = {}
        self.spawned_at: dict[str, float] = {}
        self.stopped: set[str] = set()
        self._lock = threading.Lock()

    def start(self, account: str | None = None) -> None:
        with self._lock:
            for acct in [account] if account else self.accounts:
                p = self.procs.get(acct)
                if p is not None and p.poll() is None:
                    continue
                hb = self.state_dir / "workers" / f"{acct}.json"
                hb.unlink(missing_ok=True)  # never report a previous run's heartbeat
                log = self.state_dir / "workers" / f"{acct}.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                self.procs[acct] = subprocess.Popen(
                    [*self.command, "--account", acct, "--poll", str(self.poll)],
                    stdout=log.open("ab"),
                    stderr=subprocess.STDOUT,
                    env={**os.environ, **(self.env or {})},
                    start_new_session=True,  # a signal to the API never cascades
                )
                self.spawned_at[acct] = time.time()
                self.stopped.discard(acct)

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

    def status(self, account: str, now: float | None = None) -> WorkerStatus:
        now = time.time() if now is None else now
        p = self.procs.get(account)
        st = WorkerStatus(account=account, state="not_started")
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
            if st.started_at and hb.get("ready_at"):
                st.startup_s = round(hb["ready_at"] - st.started_at, 2)
        code = p.poll()
        stats = None if code is not None else proc_stats(p.pid)
        if code is not None or stats is None:
            st.exit_code = code if code is not None else p.wait()
            st.state = "stopped" if account in self.stopped else "exited"
            return st
        st.rss_mb, st.cpu_s = stats
        if st.last_heartbeat is None:
            st.state = "starting"
        elif now - st.last_heartbeat > HEARTBEAT_STALE_S:
            st.state = "stale"
        else:
            st.state = "ready"
        return st

    def ready(self) -> bool:
        return all(self.status(a).state == "ready" for a in self.accounts)

    def snapshot(self) -> list[dict]:
        return [asdict(self.status(a)) for a in self.accounts]
