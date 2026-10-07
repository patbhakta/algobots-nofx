"""Per-worker isolation launcher (ALG-3259, A06 slice 3).

The supervisor wraps every worker command with this module:

    python -m algobots.engine.workers.sandbox --account laya --state-dir D \\
        [--uid 10001 --gid 10001] [--mem-mb 3072] [--nice 10] -- <worker command...>

It runs in the child before the worker, so nothing here needs threads or
``preexec_fn``. In order, it:

1. applies rlimits: ``RLIMIT_AS`` (address space, the per-worker memory cap),
   ``RLIMIT_NOFILE``, ``RLIMIT_CORE=0``, and lowers CPU priority (``nice``);
2. tries to move into a fresh network namespace (``unshare(CLONE_NEWNET)``),
   which leaves only a down loopback, so there is no broker egress. This needs
   ``CAP_SYS_ADMIN``. Without it (the API container) egress is only asserted
   and reported as such: no live client, no broker credentials in env;
3. drops to the non-root ``--uid``/``--gid``, with no supplementary groups;
4. checks the forbidden paths (research code, ``stock-vaults``). With a
   dropped UID each must be absent or unreadable; as root they're only reported;
5. writes ``<state_dir>/workers/<account>.sandbox.json`` with what was
   *enforced* and what was only *asserted*, then ``exec``s the worker.

A requested control that can't be applied (uid drop, rlimit, a readable
forbidden path) fails closed with ``EXIT_SANDBOX`` before the worker runs.
The environment arrives already scoped by ``scoped_env`` (supervisor side).

Stdlib only.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from pathlib import Path

EXIT_SANDBOX = 78  # EX_CONFIG: a required isolation control could not be applied

# Non-secret worker configuration and runtime plumbing; everything else is dropped.
ENV_ALLOW = ("PATH", "LANG", "LC_ALL", "TZ", "PYTHONPATH", "PYTHONUNBUFFERED", "VIRTUAL_ENV")
ENV_ALLOW_PREFIXES = ("ALGOBOTS_DEMO_",)
# Research code and the vault must never be visible to a trading worker.
FORBIDDEN_PATHS = ("/root/repos", "/opt/stock-vaults", "/root/stock-vaults", "/data/stock-vaults")


def account_secret_prefix(account: str) -> str:
    """Env prefix carrying one account's secrets, e.g. ``ALGOBOTS_ACCT_LAYA_``."""
    return f"ALGOBOTS_ACCT_{account.upper()}_"


def scoped_env(account: str, environ: dict[str, str]) -> dict[str, str]:
    """The worker's environment: the allowlist plus this account's own secrets only.

    API secrets (JWT, credential key, DATABASE_URL), broker keys and other
    accounts' ``ALGOBOTS_ACCT_<X>_*`` entries never reach the worker.
    """
    own = account_secret_prefix(account)
    return {
        k: v
        for k, v in environ.items()
        if k in ENV_ALLOW
        or k.startswith(ENV_ALLOW_PREFIXES)
        or (k.startswith(own) and not k.startswith("ALGOBOTS_DEMO_"))
    }


def _rlimit(name: str, limit: int) -> None:
    res = getattr(resource, name)
    soft, hard = resource.getrlimit(res)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(res, (limit, limit))


def _unshare_net() -> str | None:
    """Enter a new network namespace; None on success, else why not."""
    if not hasattr(os, "unshare"):
        return "os.unshare unavailable"
    try:
        os.unshare(os.CLONE_NEWNET)
    except OSError as e:
        return f"unshare(CLONE_NEWNET) refused: {e.strerror}"
    return None


def _path_exposure(path: str) -> str:
    if not os.path.lexists(path):
        return "absent"
    return "readable" if os.access(path, os.R_OK | os.X_OK) else "unreadable"


def apply(a: argparse.Namespace) -> dict:
    """Apply the controls in order; returns the report. Raises SystemExit to fail closed."""
    report: dict = {"account": a.account, "pid": os.getpid(), "at": time.time()}
    enforced: dict = {}
    asserted: dict = {}
    failures: list[str] = []
    try:
        mem = a.mem_mb * 2**20
        _rlimit("RLIMIT_AS", mem)
        _rlimit("RLIMIT_NOFILE", 1024)
        _rlimit("RLIMIT_CORE", 0)
        enforced["rlimit_as_mb"] = a.mem_mb
        enforced["rlimit_nofile"] = 1024
        enforced["rlimit_core"] = 0
    except (OSError, ValueError) as e:
        failures.append(f"rlimit: {e}")
    if a.nice:
        os.nice(a.nice)
        enforced["nice"] = os.getpriority(os.PRIO_PROCESS, 0)
    asserted["cpu"] = "no CPU-rate cap per worker; nice only (see deploy/workers/README.md)"

    why = _unshare_net() if a.netns else "not requested"
    if why is None:
        enforced["network"] = "own netns, loopback only: no egress"
    else:
        asserted["network"] = f"shared netns ({why}); paper-only, no live client in-process"

    if a.uid is not None:
        try:
            os.setgroups([])
            os.setgid(a.gid if a.gid is not None else a.uid)
            os.setuid(a.uid)
        except OSError as e:
            failures.append(f"uid drop to {a.uid}: {e}")
    if os.geteuid() == 0:
        if a.uid is not None:
            failures.append("still uid 0 after drop")
        asserted["uid"] = "root (no --uid given)"
    else:
        enforced["uid"], enforced["gid"] = os.getuid(), os.getgid()
        enforced["groups"] = os.getgroups()

    exposure = {p: _path_exposure(p) for p in a.forbid}
    readable = [p for p, s in exposure.items() if s == "readable"]
    if a.uid is not None:  # only a dropped UID can be held to this; root reads everything
        failures += [f"forbidden path readable: {p}" for p in readable]
        enforced["forbidden_paths"] = exposure
    else:
        asserted["forbidden_paths"] = exposure
    enforced["env_keys"] = sorted(os.environ)
    asserted["broker"] = "paper venue only; the worker builds no live data/exec client"

    report.update(enforced=enforced, asserted=asserted, failures=failures, ok=not failures)
    out = Path(a.state_dir) / "workers" / f"{a.account}.sandbox.json"
    try:
        out.write_text(json.dumps(report, indent=1))
    except OSError as e:
        print(f"sandbox: can't write {out}: {e}", file=sys.stderr, flush=True)
    if failures:
        print(f"sandbox: refusing to start {a.account}: {failures}", file=sys.stderr, flush=True)
        raise SystemExit(EXIT_SANDBOX)
    return report


def parse(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    if "--" not in argv:
        raise SystemExit("usage: sandbox [options] -- <worker command...>")
    i = argv.index("--")
    ap = argparse.ArgumentParser(description="Isolate one paper worker, then exec it.")
    ap.add_argument("--account", required=True)
    ap.add_argument("--state-dir", required=True)
    ap.add_argument("--uid", type=int, default=None)
    ap.add_argument("--gid", type=int, default=None)
    ap.add_argument("--mem-mb", type=int, default=3072)
    ap.add_argument("--nice", type=int, default=10)
    ap.add_argument("--netns", action="store_true", help="try a private network namespace")
    ap.add_argument("--forbid", action="append", default=None)
    a = ap.parse_args(argv[:i])
    a.forbid = a.forbid if a.forbid is not None else list(FORBIDDEN_PATHS)
    return a, argv[i + 1 :]


def main(argv: list[str] | None = None) -> None:
    a, cmd = parse(sys.argv[1:] if argv is None else argv)
    if not cmd:
        raise SystemExit("sandbox: empty worker command")
    apply(a)
    os.execvpe(cmd[0], cmd, dict(os.environ))


if __name__ == "__main__":
    main()
