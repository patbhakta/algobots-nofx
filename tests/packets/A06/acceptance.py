"""Write artifacts/A06/acceptance.json from the A06 junit report (ALG-3258).

Each acceptance case lists the tests that prove it. A case is PASS only when
every listed test ran and passed. A failing test makes it FAIL, and a skipped
or missing test makes it PENDING with the reason. Cases whose slice hasn't
landed yet are PENDING by declaration.

    python tests/packets/A06/acceptance.py artifacts/A06/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A06" / "acceptance.json"
W = "tests/engine/workers"

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN four paper accounts WHEN started THEN four separate Nautilus processes "
        "have unique IDs and account namespaces",
        "pending": "the demo runs 3 accounts (laya/jev/coin); N->N processes and unique IDs are "
        "tested and live, but a 4-account Nautilus run is not exercised yet",
        "tests": [
            f"{W}/test_supervisor.py::test_n_accounts_n_processes_kill_one_others_keep_running",
            f"{W}/test_paper.py::test_ids_are_unique_per_account",
        ],
        "evidence": ["artifacts/A06/processes.txt", "artifacts/A06/workers-before-kill.json"],
    },
    "AC2": {
        "case": "GIVEN two authorized humans viewing one account THEN only one execution worker "
        "exists",
        "tests": [
            f"{W}/test_lease.py::test_two_supervisors_one_account_exactly_one_worker",
            f"{W}/test_lease.py::test_second_start_on_same_supervisor_is_denied_and_keeps_worker",
        ],
        "evidence": [],
    },
    "AC3": {
        "case": "GIVEN one worker crashes THEN other accounts continue and the crashed account "
        "cannot submit until recovery completes",
        "tests": [
            f"{W}/test_lease.py::test_crash_freezes_only_that_account_until_reconciled",
            f"{W}/test_paper.py::test_crash_restart_is_entry_frozen_until_reconciled",
            f"{W}/test_supervisor.py::test_n_accounts_n_processes_kill_one_others_keep_running",
        ],
        "evidence": [],
    },
    "AC4": {
        "case": "GIVEN an attempted second active worker or unknown old-process status THEN "
        "start is denied",
        "tests": [
            f"{W}/test_lease.py::test_live_pid_lease_denies_start",
            f"{W}/test_lease.py::test_unknown_owner_denies_start_until_force_release",
            f"{W}/test_lease.py::test_worker_that_loses_the_race_exits_denied",
            f"{W}/test_lease.py::test_start_all_starts_free_accounts_and_reports_denied_ones",
            f"{W}/test_lease.py::test_dead_or_reused_pid_is_taken_over",
        ],
        "evidence": [],
    },
    "AC5": {
        "case": "GIVEN the target workload THEN record measured p95 RSS/CPU; do not infer a "
        "fleet capacity without measurements",
        "pending": "A06-3: p95 RSS/CPU under the declared fixture is not measured yet",
        "tests": [],
        "evidence": [],
    },
}


def results(junit: Path) -> dict[str, tuple[str, str]]:
    """node id (path::name, params folded) -> (outcome, detail); the worst outcome wins."""
    rank = {"passed": 0, "skipped": 1, "failed": 2}
    out: dict[str, tuple[str, str]] = {}
    for tc in ET.parse(junit).iter("testcase"):
        path = tc.get("classname", "").replace(".", "/")
        node = f"{path}.py::{tc.get('name', '').split('[')[0]}"
        outcome, detail = "passed", ""
        for tag in ("failure", "error"):
            if (el := tc.find(tag)) is not None:
                outcome, detail = "failed", el.get("message", "")[:200]
        if (el := tc.find("skipped")) is not None:
            outcome, detail = "skipped", el.get("message", "")[:200]
        if node not in out or rank[outcome] > rank[out[node][0]]:
            out[node] = (outcome, detail)
    return out


def verdicts(res: dict[str, tuple[str, str]]) -> dict[str, dict]:
    report = {}
    junit_rel = "artifacts/A06/test-results/junit.xml"
    for ac, spec in CASES.items():
        tests = {t: res.get(t, ("missing", "not collected")) for t in spec["tests"]}
        failed = [t for t, (o, _) in tests.items() if o in ("failed", "missing")]
        skipped = {t: d for t, (o, d) in tests.items() if o == "skipped"}
        if any(tests[t][0] == "failed" for t in failed):
            status, note = "FAIL", f"failing: {failed}"
        elif spec.get("pending"):
            status, note = "PENDING", spec["pending"]
        elif failed or skipped or not tests:
            status, note = "PENDING", f"not run: {failed} {skipped}".strip()
        else:
            status, note = "PASS", f"{len(tests)} tests passed"
        report[ac] = {
            "status": status,
            "case": spec["case"],
            "note": note,
            "tests": {t: o for t, (o, _) in tests.items()},
            "evidence": [junit_rel, *spec["evidence"]] if tests else spec["evidence"],
        }
    return report


def main(argv: list[str]) -> int:
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A06/test-results/junit.xml"
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    cases = verdicts(results(junit))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "packet": "A06",
                "slice": "A06-2 (ALG-3258)",
                "tested_commit": head,
                "command": "make verify-A06",
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )
    for ac, v in cases.items():
        print(f"{ac}: {v['status']} — {v['note']}")
    return 1 if any(v["status"] == "FAIL" for v in cases.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
