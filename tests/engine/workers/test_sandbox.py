"""ALG-3259 worker isolation: scoped env, rlimits, non-root UID, fail-closed forbidden paths."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from algobots.engine.workers.sandbox import EXIT_SANDBOX, scoped_env
from algobots.engine.workers.supervisor import Isolation, Supervisor

NOBODY = 65534
SRC = str(Path(__file__).resolve().parents[3] / "src")
as_root = pytest.mark.skipif(os.geteuid() != 0, reason="dropping to another UID needs root")

PROBE = (
    "import json, os, resource, sys; print(json.dumps({'uid': os.getuid(), 'gid': os.getgid(),"
    " 'groups': os.getgroups(), 'as': resource.getrlimit(resource.RLIMIT_AS)[0],"
    " 'nice': os.getpriority(os.PRIO_PROCESS, 0), 'env': sorted(os.environ)}))"
)


@pytest.fixture
def shared_dir():
    """A state dir the dropped UID can reach (pytest's tmp_path is root-only)."""
    d = Path(tempfile.mkdtemp(prefix="alg3259-", dir="/tmp"))
    d.chmod(0o777)
    (d / "workers").mkdir()
    (d / "workers").chmod(0o777)
    yield d
    shutil.rmtree(d, ignore_errors=True)


def _sandbox(state: Path, *opts: str, cmd: list[str] | None = None):
    return subprocess.run(
        [sys.executable, "-m", "algobots.engine.workers.sandbox", "--account", "syn1"]
        + ["--state-dir", str(state), *opts, "--", *(cmd or [sys.executable, "-c", PROBE])],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], "PYTHONPATH": SRC, "ALGOBOTS_ACCT_SYN1_KEY": "k1"},
        timeout=30,
    )


def test_scoped_env_keeps_only_this_accounts_secrets():
    env = {
        "PATH": "/bin",
        "DATABASE_URL": "postgresql://paperclip",
        "ALGOBOTS_JWT_SECRET": "s",
        "ALGOBOTS_CREDENTIAL_ENCRYPTION_KEY": "c",
        "KALSHI_API_KEY": "live",
        "ALGOBOTS_DEMO_STATE_DIR": "/state",
        "ALGOBOTS_ACCT_SYN1_KEY": "mine",
        "ALGOBOTS_ACCT_SYN2_KEY": "theirs",
        "ALGOBOTS_ACCT_SYN10_KEY": "prefix-collision",
    }
    assert scoped_env("syn1", env) == {
        "PATH": "/bin",
        "ALGOBOTS_DEMO_STATE_DIR": "/state",
        "ALGOBOTS_ACCT_SYN1_KEY": "mine",
    }


def test_isolation_from_env():
    iso = Isolation.from_env({"ALGOBOTS_WORKER_UID": "10001", "ALGOBOTS_WORKER_MEM_MB": "2048"})
    assert (iso.uid, iso.gid, iso.mem_mb) == (10001, None, 2048)
    argv = iso.argv("syn1", Path("/s"))
    assert argv[-1] == "--" and argv[argv.index("--gid") + 1] == "10001"
    assert "--uid" not in Isolation.from_env({}).argv("syn1", Path("/s"))


@as_root
def test_sandbox_drops_uid_applies_rlimits_and_reports(shared_dir):
    locked = shared_dir / "research"
    locked.mkdir(mode=0o700)
    r = _sandbox(shared_dir, "--uid", str(NOBODY), "--mem-mb", "1024", "--forbid", str(locked))
    assert r.returncode == 0, r.stderr
    seen = json.loads(r.stdout)
    assert seen["uid"] == seen["gid"] == NOBODY and seen["groups"] == []
    assert seen["as"] == 1024 * 2**20 and seen["nice"] >= 10
    # LC_CTYPE is Python's own C-locale coercion (PEP 538), not inherited
    assert set(seen["env"]) - {"LC_CTYPE"} == {"ALGOBOTS_ACCT_SYN1_KEY", "PATH", "PYTHONPATH"}
    rep = json.loads((shared_dir / "workers" / "syn1.sandbox.json").read_text())
    assert rep["ok"] and rep["enforced"]["uid"] == NOBODY
    assert rep["enforced"]["forbidden_paths"] == {str(locked): "unreadable"}
    assert "network" in rep["enforced"] or "network" in rep["asserted"]


@as_root
def test_sandbox_fails_closed_on_a_readable_forbidden_path(shared_dir):
    leak = shared_dir / "stock-vaults"
    leak.mkdir(mode=0o755)
    marker = shared_dir / "ran"
    r = _sandbox(
        shared_dir,
        *("--uid", str(NOBODY), "--forbid", str(leak)),
        cmd=["touch", str(marker)],
    )
    assert r.returncode == EXIT_SANDBOX and not marker.exists()
    rep = json.loads((shared_dir / "workers" / "syn1.sandbox.json").read_text())
    assert not rep["ok"] and rep["failures"] == [f"forbidden path readable: {leak}"]


def test_sandbox_without_uid_only_asserts(tmp_path):
    (tmp_path / "workers").mkdir()
    r = _sandbox(tmp_path, "--forbid", str(tmp_path))
    assert r.returncode == 0, r.stderr
    rep = json.loads((tmp_path / "workers" / "syn1.sandbox.json").read_text())
    if os.geteuid() == 0:
        assert "uid" in rep["asserted"] and "forbidden_paths" in rep["asserted"]
    assert rep["enforced"]["rlimit_core"] == 0


@as_root
def test_supervised_worker_runs_as_non_root_uid(shared_dir):
    script = shared_dir / "w.py"
    script.write_text(
        "import argparse, json, os, sys, time\n"
        "ap = argparse.ArgumentParser(); ap.add_argument('--account'); ap.add_argument('--poll')\n"
        "a = ap.parse_args()\n"
        "p = os.path.join(os.environ['ALGOBOTS_DEMO_STATE_DIR'], 'workers', a.account + '.json')\n"
        "while True:\n"
        "    open(p, 'w').write(json.dumps({'pid': os.getpid(), 'last_heartbeat': time.time(),"
        " 'reconciled': True, 'phase': 'ready'}))\n"
        "    time.sleep(0.1)\n"
    )
    script.chmod(0o644)
    locked = shared_dir / "research"
    locked.mkdir(mode=0o700)
    sup = Supervisor(
        ["syn1"],
        shared_dir,
        poll=0.1,
        command=[sys.executable, str(script)],
        env={"ALGOBOTS_DEMO_STATE_DIR": str(shared_dir), "PYTHONPATH": SRC},
        isolation=Isolation(uid=NOBODY, forbid=(str(locked),)),
    )
    sup.start()
    try:
        end = time.monotonic() + 15
        while time.monotonic() < end and sup.status("syn1").state != "ready":
            time.sleep(0.05)
        st = sup.status("syn1")
        assert st.state == "ready", (shared_dir / "workers" / "syn1.log").read_text()
        assert st.uid == NOBODY
    finally:
        sup.stop()
    assert sup.status("syn1").state == "stopped"
