"""A06 packet checks (ALG-3258): the acceptance map points at real tests; lease keying."""

import subprocess
import sys
from pathlib import Path

from algobots.engine.workers.lease import ENVIRONMENT, TENANT, Lease

sys.path.insert(0, str(Path(__file__).parent))
import acceptance as A  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]


def test_every_acceptance_test_id_is_collected():
    out = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-o",
            "addopts=",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/engine/workers",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    collected = {line.split("[")[0] for line in out.splitlines() if "::" in line}
    mapped = {t for c in A.CASES.values() for t in c["tests"]}
    paper = {t for t in mapped if "test_paper.py" in t}
    # test_paper needs nautilus_trader; when it's absent the verdict says PENDING, not PASS
    assert mapped - paper <= collected
    assert not (paper & collected) or paper <= collected


def test_ac2_to_ac4_are_not_declared_pending_and_ac5_is():
    assert all(
        not A.CASES[ac].get("pending") and A.CASES[ac]["tests"] for ac in ("AC2", "AC3", "AC4")
    )
    assert A.CASES["AC5"]["pending"]


def test_verdicts_fail_closed():
    ok = {t: ("passed", "") for c in A.CASES.values() for t in c["tests"]}
    v = A.verdicts(ok)
    assert [v[ac]["status"] for ac in A.CASES] == ["PENDING", "PASS", "PASS", "PASS", "PENDING"]
    one = next(iter(A.CASES["AC4"]["tests"]))
    assert A.verdicts({**ok, one: ("failed", "x")})["AC4"]["status"] == "FAIL"
    assert A.verdicts({**ok, one: ("skipped", "x")})["AC4"]["status"] == "PENDING"
    assert A.verdicts({k: o for k, o in ok.items() if k != one})["AC4"]["status"] == "PENDING"


def test_lease_is_keyed_by_tenant_account_environment(tmp_path):
    ls = Lease(tmp_path, "laya")
    assert ls.key == f"{TENANT}.laya.{ENVIRONMENT}" == "demo.laya.paper"
    assert ls.path == tmp_path / "workers" / "leases" / "demo.laya.paper.lease"
    assert Lease(tmp_path, "laya", environment="live").path != ls.path
