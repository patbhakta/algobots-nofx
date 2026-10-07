"""Durable per-account worker ownership (ALG-3258, A06 slice 2).

One lease file per (tenant, account, environment) under
``<state_dir>/workers/leases/``. Each file holds the owner's PID, its kernel
start time (``/proc/<pid>/stat`` field 22, so a reused PID never counts as
the old owner), its host and its PID namespace. Every read-check-write runs
under an ``flock`` on a sidecar ``.lock`` file, so two supervisors or API
processes on one host can't both win.

A lease can be taken over only after the previous owner's termination is
*confirmed*: its PID is gone, a zombie, or now belongs to a different process.
If the owner is alive, the lease is denied. It is also denied when liveness
can't be determined: the lease was written on another host or PID namespace,
the file is unreadable, or ``/proc`` can't be read. The operator then runs
``force-release``:

    python -m algobots.engine.workers.lease force-release --account laya

Stdlib only.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import socket
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

TENANT = "demo"
ENVIRONMENT = "paper"
EXIT_DENIED = 75  # EX_TEMPFAIL: a worker that can't own its account exits with this


class LeaseDenied(RuntimeError):
    """``start`` refused: the account is (or may be) owned by another process."""

    def __init__(self, account: str, reason: str, holder: dict | None = None) -> None:
        super().__init__(f"{account}: {reason}")
        self.account, self.reason, self.holder = account, reason, holder


def proc_start_time(pid: int) -> int | None:
    """Kernel start time (clock ticks since boot) of a live, non-zombie PID; None if it's gone.

    Raises ``PermissionError`` / ``OSError`` when ``/proc`` can't answer.
    """
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    except (FileNotFoundError, ProcessLookupError):
        return None
    if fields[0] in ("Z", "X"):  # exited, not yet reaped
        return None
    return int(fields[19])


def _pidns() -> str | None:
    try:
        return os.readlink("/proc/self/ns/pid")
    except OSError:
        return None


def identity(pid: int) -> dict:
    return {
        "pid": pid,
        "start_time": proc_start_time(pid),
        "host": socket.gethostname(),
        "pidns": _pidns(),
    }


@dataclass
class Holder:
    """Who holds a lease: ``free`` / ``dead`` (takeover allowed) / ``live`` / ``unknown``."""

    status: str
    reason: str
    lease: dict | None = None


def inspect(lease: dict | None) -> Holder:
    if lease is None:
        return Holder("free", "no lease")
    try:
        pid, start = int(lease["pid"]), lease["start_time"]
        host, pidns = lease["host"], lease["pidns"]
    except (KeyError, TypeError, ValueError):
        return Holder("unknown", "lease file unreadable; owner liveness unknown", lease)
    if host != socket.gethostname() or pidns is None or pidns != _pidns():
        return Holder(
            "unknown",
            f"lease held by pid {pid} on {host} ({pidns}); liveness can't be confirmed from here",
            lease,
        )
    try:
        now_start = proc_start_time(pid)
    except OSError as e:
        return Holder("unknown", f"can't read /proc for pid {pid}: {e}", lease)
    if now_start is None:
        return Holder("dead", f"previous owner pid {pid} has terminated", lease)
    if start is None or now_start != start:
        return Holder("dead", f"previous owner pid {pid} has terminated (pid reused)", lease)
    return Holder("live", f"lease held by live pid {pid}", lease)


class Lease:
    def __init__(
        self, state_dir: Path, account: str, tenant: str = TENANT, environment: str = ENVIRONMENT
    ) -> None:
        self.account = account
        self.key = f"{tenant}.{account}.{environment}"
        self.path = Path(state_dir) / "workers" / "leases" / f"{self.key}.lease"

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path.with_suffix(".lock"), "a") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    def read(self) -> dict | None:
        """The lease content; ``{}`` if the file exists but is corrupt."""
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def holder(self) -> Holder:
        return inspect(self.read())

    def owned_by(self, pid: int) -> bool:
        lease = self.read()
        return bool(lease) and lease.get("pid") == pid and inspect(lease).status == "live"

    def check(self) -> Holder:
        """Raise ``LeaseDenied`` unless the lease is free or its owner is confirmed dead.

        Call with ``locked()`` held when acting on the answer.
        """
        h = self.holder()
        if h.status in ("live", "unknown"):
            raise LeaseDenied(self.account, h.reason, h.lease)
        return h

    def write(self, pid: int) -> dict:
        """Record ``pid`` as owner. Call with ``locked()`` held, after ``check()``."""
        lease = {**identity(pid), "key": self.key, "acquired_at": time.time()}
        tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(lease))
        tmp.replace(self.path)
        return lease

    def acquire(self, pid: int | None = None) -> dict:
        """Take the lease for ``pid`` (default: this process); idempotent for the owner."""
        pid = os.getpid() if pid is None else pid
        with self.locked():
            if self.owned_by(pid):
                return self.read() or {}
            self.check()
            return self.write(pid)

    def release(self, pid: int) -> bool:
        """Drop the lease if ``pid`` owns it (live, or exited and not reused)."""
        with self.locked():
            lease = self.read()
            if not lease or lease.get("pid") != pid or inspect(lease).status == "unknown":
                return False
            self.path.unlink(missing_ok=True)
            return True

    def force_release(self) -> Holder:
        """Operator override for the uncertain case; refuses while the owner is alive."""
        with self.locked():
            h = self.holder()
            if h.status == "live":
                raise LeaseDenied(self.account, h.reason + "; stop it first", h.lease)
            self.path.unlink(missing_ok=True)
            return h


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Inspect or force-release a paper worker lease.")
    ap.add_argument("command", choices=["show", "force-release"])
    ap.add_argument("--account", required=True)
    ap.add_argument("--state-dir", default=None, help="default: ALGOBOTS demo_state_dir")
    a = ap.parse_args(argv)
    state_dir = a.state_dir
    if state_dir is None:
        from algobots.api.config import get_settings

        state_dir = get_settings().demo_state_dir
    lease = Lease(Path(state_dir), a.account)
    if a.command == "show":
        h = lease.holder()
        print(
            json.dumps(
                {"path": str(lease.path), "status": h.status, "reason": h.reason, "lease": h.lease}
            )
        )
        return
    try:
        h = lease.force_release()
    except LeaseDenied as e:
        raise SystemExit(f"refused: {e}") from None
    print(f"released {lease.path} (was: {h.status}: {h.reason})")


if __name__ == "__main__":
    main()
