"""Write artifacts/A02/acceptance.json from the A02 junit report (ALG-3098).

Each acceptance case lists the tests that prove it. A case is PASS only
when every listed test ran and passed. A failing test makes it FAIL, and a
skipped or missing test makes it PENDING with the reason.

    python tests/packets/A02/acceptance.py artifacts/A02/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A02" / "acceptance.json"
P = "tests.packets.A02.test_acceptance"
Q = "tests.agent_queue.test_authority"

# Independent review receipt (static evidence; ALG-3322 verdict comment).
# Filled in as reviews land: the reviewed commit and verdict are data, not
# derived from the junit, so rerunning this script reproduces them exactly.
REVIEW = {
    "issue": "ALG-3322",
    "reviewed_commit": "87f5ad4",
    "verdict": "PASS",
    "note": "AC1-AC4 PASS; 5 non-blocking findings (F1-F5) fixed in follow-up "
            "commits on the same branch, delta re-reviewed before integration",
}

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN two (or more) concurrent claimants THEN exactly one active "
        "claim exists on the task",
        "tests": [
            f"{P}::test_ac1_concurrent_processes_produce_exactly_one_active_claim",
            f"{P}::test_ac1_concurrent_threads_produce_exactly_one_active_claim",
            f"{Q}.TestClaim::test_second_claim_while_lease_live_is_denied",
            f"{Q}.TestClaim::test_expired_lease_is_reclaimable_and_bumps_epoch",
        ],
        "evidence": ["artifacts/A02/demo-run.json"],
    },
    "AC2": {
        "case": "GIVEN an expired or revoked attempt THEN it can neither merge "
        "(integrate) nor publish a current completion",
        "tests": [
            f"{P}::test_ac2_expired_attempt_cannot_complete",
            f"{P}::test_ac2_revoked_attempt_cannot_publish_after_reclaim",
            f"{Q}.TestStaleAttempts::test_expired_attempt_cannot_complete",
            f"{Q}.TestStaleAttempts::test_expired_attempt_cannot_integrate_after_passing",
            f"{Q}.TestStaleAttempts::test_revoked_attempt_cannot_publish_after_reclaim",
        ],
        "evidence": [],
    },
    "AC3": {
        "case": "GIVEN a failed integration THEN dependents stay ineligible despite "
        "passing branch tests",
        "tests": [
            f"{P}::test_ac3_failed_integration_leaves_dependents_ineligible",
            f"{Q}.TestCompleteAndIntegrate::test_complete_passed_waits_for_integration",
            f"{Q}.TestCompleteAndIntegrate::test_happy_path_to_done_makes_dependent_claimable",
        ],
        "evidence": [],
    },
    "AC4": {
        "case": "GIVEN budget exhaustion THEN the task checkpoints as BLOCKED with a "
        "published reason and no retry loop can continue",
        "tests": [
            f"{P}::test_ac4_budget_exhaustion_checkpoints_without_retry_loop",
            f"{Q}.TestBudgetsAndBlocking::test_budget_exhaustion_checkpoints_blocked_no_loop",
            f"{Q}.TestBudgetsAndBlocking::test_reclaim_loop_also_terminates_in_blocked",
            f"{Q}.TestBudgetsAndBlocking::test_same_failure_repair_cap_blocks",
            f"{Q}.TestBudgetsAndBlocking::test_blocked_state_is_durable_and_inspectable",
            f"{Q}.TestBudgetsAndBlocking::test_claim_path_budget_block_is_durable",
            f"{Q}.TestBudgetsAndBlocking::test_blocked_checkpoint_releases_resources",
            f"{Q}.TestBudgetsAndBlocking::test_dead_holder_does_not_strand_a_resource",
        ],
        "evidence": ["artifacts/A02/demo-run.json"],
    },
}


def results(junit: Path) -> dict[str, tuple[str, str]]:
    """junit id (classname::name, params folded) -> (outcome, detail); worst wins."""
    rank = {"passed": 0, "skipped": 1, "failed": 2}
    out: dict[str, tuple[str, str]] = {}
    for tc in ET.parse(junit).iter("testcase"):
        node = f"{tc.get('classname', '')}::{tc.get('name', '').split('[')[0]}"
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
    junit_rel = "artifacts/A02/test-results/junit.xml"
    for ac, spec in CASES.items():
        tests = {t: res.get(t, ("missing", "not collected")) for t in spec["tests"]}
        failed = [t for t, (o, _) in tests.items() if o in ("failed", "missing")]
        skipped = {t: d for t, (o, d) in tests.items() if o == "skipped"}
        if any(tests[t][0] == "failed" for t in failed):
            status, note = "FAIL", f"failing: {failed}"
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
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A02/test-results/junit.xml"
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    cases = verdicts(results(junit))
    # tested_commit is always the commit the tests actually ran at (ALG-3322
    # F3: never carry an older sha forward, however green the verdicts are).
    tested_commit = head
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "packet": "A02",
                "slice": "A02 sprint-1 (ALG-3098): transactional claims + leases",
                "tested_commit": tested_commit,
                "command": "make verify-A02",
                "review": REVIEW,
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
