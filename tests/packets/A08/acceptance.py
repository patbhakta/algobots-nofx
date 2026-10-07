"""Write artifacts/A08/acceptance.json from the A08 junit report (ALG-3104).

Each acceptance case lists the tests that prove it. A case is PASS only when
every listed test ran and passed. A failing test makes it FAIL, and a skipped
or missing test makes it PENDING with the reason (fail-closed, A06/A07 pattern).

    python tests/packets/A08/acceptance.py artifacts/A08/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A08" / "acceptance.json"
W = "tests/packets/A08"
R = "tests/risk"

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN $1,000 available and two simultaneous $700 entry plans "
        "THEN both cannot be admitted; sum of reservations never exceeds "
        "permitted funds",
        "tests": [
            f"{W}/test_ac1_race.py::test_ac1_sequential_second_700_is_rejected",
            f"{W}/test_ac1_race.py::test_ac1_concurrent_700s_exactly_one_admitted",
            f"{W}/test_ac1_race.py::test_release_returns_funds_and_admits_the_waiter",
            f"{W}/test_ac1_race.py::test_reservations_never_commit_without_their_intent",
            f"{W}/test_ac2_uncertain.py::test_db_check_released_row_requires_reason",
        ],
        "evidence": ["artifacts/A08/demo-run.json"],
    },
    "AC2": {
        "case": "GIVEN an unknown order or cancel-pending remainder THEN its "
        "reservation cannot fund a new conflicting entry",
        "tests": [
            f"{W}/test_ac2_uncertain.py::test_unknown_order_reservation_cannot_fund_new_entry",
            f"{W}/test_ac2_uncertain.py::test_cancel_pending_remainder_retains_obligation",
            f"{W}/test_ac2_uncertain.py::test_double_release_is_rejected",
            f"{W}/test_ac2_uncertain.py::test_release_requires_a_known_reason",
        ],
        "evidence": ["artifacts/A08/demo-run.json"],
    },
    "AC3": {
        "case": "GIVEN a breached daily loss cap THEN new entries are denied "
        "while correctly scoped risk-reducing actions remain possible",
        "tests": [
            f"{W}/test_ac3_ac4_ac5.py::test_ac3_daily_loss_breach_denies_entries_allows_risk_reducing",
            f"{W}/test_ac3_ac4_ac5.py::test_ac3_entry_pause_via_controls_denies_entries_not_reductions",
            f"{R}/test_policy.py::test_daily_loss_denies_entry_but_exit_passes_uncapped",
            f"{R}/test_daily_loss.py::test_loss_equal_to_cap_trips",
        ],
        "evidence": ["artifacts/A08/demo-run.json"],
    },
    "AC4": {
        "case": "GIVEN an AI proposal requesting greater leverage/size THEN "
        "deterministic policy rejects or clamps it with an explicit audit reason",
        "tests": [
            f"{W}/test_ac3_ac4_ac5.py::test_ac4_oversize_ai_proposal_rejected_then_admitted_at_clamped_size",
            f"{R}/test_policy.py::test_ai_oversize_request_is_clamped_with_explicit_reason",
            f"{R}/test_policy.py::test_same_inputs_same_decision_always",
            f"{R}/test_policy.py::test_first_rule_wins_permission_beats_everything",
        ],
        "evidence": ["artifacts/A08/demo-run.json"],
    },
    "AC5": {
        "case": "GIVEN a reconnect or stale mark THEN protection status is "
        "visible and new risk is blocked until required state is fresh",
        "tests": [
            f"{W}/test_ac3_ac4_ac5.py::test_ac5_stale_mark_blocks_new_risk_until_fresh",
            f"{W}/test_ac3_ac4_ac5.py::test_ac5_protection_status_visible_during_outage",
            f"{R}/test_policy.py::test_stale_mark_blocks_entry_but_not_exit",
            f"{R}/test_policy.py::test_disconnect_blocks_entry",
            f"{R}/test_controls.py::test_protection_status_lists_working_and_paused_stops",
        ],
        "evidence": ["artifacts/A08/demo-run.json"],
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
    junit_rel = "artifacts/A08/test-results/junit.xml"
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
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A08/test-results/junit.xml"
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
                "packet": "A08",
                "slice": "A08 packet (ALG-3104)",
                "tested_commit": tested_commit,
                "command": "make verify-A08",
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
