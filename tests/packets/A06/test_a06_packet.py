"""A06 packet checks (ALG-3258): the acceptance map points at real tests; lease keying."""

import json
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
            "tests/packets/A06",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    ).stdout
    collected = {line.split("[")[0] for line in out.splitlines() if "::" in line}
    mapped = {t for c in A.CASES.values() for t in c["tests"]}
    paper = {t for t in mapped if "test_paper.py" in t or "test_fixture.py" in t}
    # these need nautilus_trader; when it's absent the verdict says PENDING, not PASS
    assert mapped - paper <= collected
    assert not (paper & collected) or paper <= collected


def test_no_case_is_declared_pending():
    assert all(not c.get("pending") and c["tests"] for c in A.CASES.values())


def test_measurements_are_committed_and_complete():
    m = json.loads((ROOT / "artifacts/A06/measurements.json").read_text())
    assert m["fixture"]["accounts"] == ["syn1", "syn2", "syn3", "syn4"]
    assert m["fixture"]["deployments"] == 8 and len(m["workers"]) == 4
    pooled = m["pooled"]
    for k in ("rss_mb", "cpu_pct_of_one_core", "startup_s", "callback_latency_ms"):
        assert pooled[k]["p50"] is not None and pooled[k]["p95"] is not None, k
    assert pooled["queue_depth_p95_max"] is not None and pooled["queue_age_ms_p95_max"] is not None
    assert m["capacity_extrapolation"] is None  # AC5: never infer a fleet capacity


def test_verdicts_fail_closed():
    ok = {t: ("passed", "") for c in A.CASES.values() for t in c["tests"]}
    v = A.verdicts(ok)
    assert [v[ac]["status"] for ac in A.CASES] == ["PASS"] * 5
    one = next(iter(A.CASES["AC4"]["tests"]))
    assert A.verdicts({**ok, one: ("failed", "x")})["AC4"]["status"] == "FAIL"
    assert A.verdicts({**ok, one: ("skipped", "x")})["AC4"]["status"] == "PENDING"
    assert A.verdicts({k: o for k, o in ok.items() if k != one})["AC4"]["status"] == "PENDING"


def test_lease_is_keyed_by_tenant_account_environment(tmp_path):
    ls = Lease(tmp_path, "laya")
    assert ls.key == f"{TENANT}.laya.{ENVIRONMENT}" == "demo.laya.paper"
    assert ls.path == tmp_path / "workers" / "leases" / "demo.laya.paper.lease"
    assert Lease(tmp_path, "laya", environment="live").path != ls.path
