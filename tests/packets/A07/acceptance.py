"""Write artifacts/A07/acceptance.json from the A07 junit report (ALG-3103).

Each acceptance case lists the tests that prove it. A case is PASS only when
every listed test ran and passed. A failing test makes it FAIL, and a skipped
or missing test makes it PENDING with the reason (fail-closed, A06 pattern).

    python tests/packets/A07/acceptance.py artifacts/A07/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A07" / "acceptance.json"
W = "tests/execution/ledger"

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN one request sent 1,000 times concurrently THEN one intent exists "
        "and at most one confirmed external order is created",
        "tests": [
            f"{W}/test_commit_dedup.py::test_ac1_one_request_sent_1000_times_concurrently_yields_one_intent",
            f"{W}/test_commit_dedup.py::test_active_entry_guard_blocks_same_business_signal_with_different_keys",
            f"{W}/test_outbox_replay.py::test_staging_is_idempotent_per_epoch_and_versioned_across_epochs",
        ],
        "evidence": ["artifacts/A07/demo-run.json"],
    },
    "AC2": {
        "case": "GIVEN identical key with changed quantity THEN request is rejected "
        "without altering the original intent",
        "tests": [
            f"{W}/test_commit_dedup.py::test_ac2_same_key_changed_payload_is_rejected_original_untouched",
        ],
        "evidence": ["artifacts/A07/demo-run.json"],
    },
    "AC3": {
        "case": "GIVEN broker accepts then connection times out THEN status becomes "
        "UNKNOWN and no blind resubmit occurs; reconciliation finds the original order",
        "tests": [
            f"{W}/test_accept_timeout.py::test_ac3_accept_before_timeout_becomes_unknown_without_blind_resubmit",
            f"{W}/test_accept_timeout.py::test_unknown_cannot_be_exited_by_a_non_reconciliation_event",
            f"{W}/test_accept_timeout.py::test_connection_drop_stays_pending_and_recovers_via_replay",
            f"{W}/test_state_machine.py::test_unknown_exit_requires_reconciliation",
        ],
        "evidence": ["artifacts/A07/demo-run.json"],
    },
    "AC4": {
        "case": "GIVEN a fill repeated or delivered out of order THEN cumulative fill, "
        "cash, and fees are correct exactly once in projections",
        "tests": [
            f"{W}/test_fills_dedup.py::test_ac4_duplicate_fill_settles_exactly_once",
            f"{W}/test_fills_dedup.py::test_ac4_partial_then_full_fill_projection",
            f"{W}/test_fills_dedup.py::test_ac4_out_of_order_delivery_is_cumulative_correct",
            f"{W}/test_fills_dedup.py::test_ac4_fill_before_acknowledgment_is_deferred_not_dropped",
            f"{W}/test_fills_dedup.py::test_ac4_delayed_cancel_after_partial_fill",
        ],
        "evidence": ["artifacts/A07/demo-run.json"],
    },
    "AC5": {
        "case": "GIVEN no client-ID lookup and ambiguous existence THEN the account "
        "remains frozen for conflicting entries until operator resolution",
        "tests": [
            f"{W}/test_account_freeze.py::test_ac5_ambiguous_existence_without_lookup_freezes_account",
            f"{W}/test_account_freeze.py::test_freeze_is_idempotent_one_active_row",
            f"{W}/test_account_freeze.py::test_freeze_is_tenant_scoped",
            f"{W}/test_commit_dedup.py::test_frozen_account_rejects_entries_but_not_cancels",
        ],
        "evidence": ["artifacts/A07/demo-run.json"],
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
    junit_rel = "artifacts/A07/test-results/junit.xml"
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
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A07/test-results/junit.xml"
    head = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True
    ).stdout.strip()
    cases = verdicts(results(junit))
    tested_commit = head
    if OUT.exists():
        try:
            old = json.loads(OUT.read_text())
            if old.get("tested_commit") and old.get("cases") == cases:
                tested_commit = old["tested_commit"]
        except Exception:
            pass
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {
                "packet": "A07",
                "slice": "A07 packet (ALG-3103)",
                "tested_commit": tested_commit,
                "command": "make verify-A07",
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
