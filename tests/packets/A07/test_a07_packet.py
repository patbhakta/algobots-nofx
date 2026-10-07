"""A07 packet self-checks: acceptance map integrity, fail-closed verdicts,
contract registrations, and the schema lock (A06 packet pattern)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # tests/ for packet imports

from tests.execution.ledger.conftest import REPO_ROOT  # noqa: E402
from tests.packets.A07 import acceptance  # noqa: E402


def test_every_acceptance_test_id_is_collected():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "tests/execution/ledger"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(REPO_ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    collected = proc.stdout
    missing = [
        test
        for spec in acceptance.CASES.values()
        for test in spec["tests"]
        if test not in collected
    ]
    assert not missing, f"acceptance tests not collected: {missing}"


def test_no_case_is_declared_pending():
    assert all("pending" not in spec for spec in acceptance.CASES.values())


def test_verdicts_fail_closed():
    res = {t: ("passed", "") for spec in acceptance.CASES.values() for t in spec["tests"]}
    cases = acceptance.verdicts(res)
    assert all(v["status"] == "PASS" for v in cases.values())

    one = next(iter(spec["tests"] for spec in acceptance.CASES.values()))[0]
    res[one] = ("skipped", "no nautilus")
    assert acceptance.verdicts(res)[next(iter(acceptance.CASES))]["status"] == "PENDING"

    res[one] = ("missing", "not collected")
    assert acceptance.verdicts(res)[next(iter(acceptance.CASES))]["status"] == "PENDING"

    res[one] = ("failed", "boom")
    assert acceptance.verdicts(res)[next(iter(acceptance.CASES))]["status"] == "FAIL"


def test_a07_contracts_are_registered_and_locked():
    from algobots.contracts import registry

    assert registry.get("OutboxEvent", "1.0").contract_name == "OutboxEvent"
    assert registry.get("IntentStatusResponse", "1.0").contract_name == "IntentStatusResponse"
    assert (
        registry.verify_lock(registry.load_lock()) == []
    ), "live registry must match schema-lock.json"


def test_demo_run_artifact_is_committed_and_complete():
    demo = REPO_ROOT / "artifacts" / "A07" / "demo-run.json"
    assert demo.exists(), "run `make demo-A07` and commit artifacts/A07/demo-run.json"
    import json

    payload = json.loads(demo.read_text())
    assert set(payload) >= {"dedup_replay", "accept_timeout"}, payload.keys()
    dedup = payload["dedup_replay"]
    assert dedup["requests"] >= 50 and dedup["intents"] == 1
    assert dedup["guard_rejections"] >= 1, "different transport keys must hit the guard"
    trace = payload["accept_timeout"]
    assert trace["final_status"] == "FILLED"
    assert trace["broker_orders"] == 1, "reconciliation finds the original, never a second order"
