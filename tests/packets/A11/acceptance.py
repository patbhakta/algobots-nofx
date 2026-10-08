"""Write artifacts/A11/acceptance.json + test-results/summary.txt (ALG-3283).

Each acceptance case lists the tests that prove it. A case is PASS only when
every listed test ran and passed. A failing test makes it FAIL, and a skipped,
missing or spec-declared-blocked case is BLOCKED with the reason (fail-closed;
A08 pattern with the A11 PASS/FAIL/BLOCKED vocabulary).

    python tests/packets/A11/acceptance.py artifacts/A11/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A11" / "acceptance.json"
SUMMARY = ROOT / "artifacts" / "A11" / "test-results" / "summary.txt"
R281 = "artifacts/A11/ALG-3281"
R282 = "artifacts/A11/ALG-3282"
AC6_BLOCKED = (
    "tenant-scoped fleet breakers (ALG-3186, commit db6f400) ride the A03 "
    "branch feat/alg-3099-a03-tenant-auth and are not on main yet; the three "
    "proving tests below run there, not here. Main still ships the per-user "
    "fleet breaker (base test listed), so the AC6 assertion cannot be proven "
    "or disproven on this commit. Unblock owner: A03 integration (ALG-3099) "
    "merges feat/alg-3099-a03-tenant-auth into main; then re-run "
    "make verify-A11 with tests/api/test_fleet_breaker_tenancy.py added to "
    "the breaker lane."
)

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN three instances of one template with different params "
        "THEN each keeps its own isolated, attributable version, orders and "
        "statistics",
        "tests": [
            "tests/demo/test_studio.py::test_dsl_templates_hash_through_dsl_and_change_with_params",
            "tests/demo/test_studio.py::test_three_template_instances_stay_attributable",
            "tests/demo/test_studio.py::test_orders_carry_live_deployment_attribution",
            "tests/engine/workers/test_template.py::test_three_instances_produce_orders_attributed_to_their_deployment",
            "tests/engine/workers/test_template.py::test_demo_page_and_api_show_template_orders_per_account",
        ],
        "evidence": [f"{R281}/README.md"],
    },
    "AC2": {
        "case": "GIVEN a running deployment WHEN its template is edited THEN "
        "the deployment keeps the frozen version it deployed with",
        "tests": [
            "tests/demo/test_studio.py::test_edit_never_changes_running_deployment",
            "tests/engine/workers/test_template.py::test_editing_the_template_mid_run_does_not_change_a_running_deployment",
            "tests/engine/workers/test_template.py::test_tampered_frozen_params_refuse_to_run",
        ],
        "evidence": [f"{R281}/README.md"],
    },
    "AC3": {
        "case": "GIVEN four accounts where one is ineligible for the strategy "
        "THEN fan-out yields three independent children and one explicit skip, "
        "in both preview and execution",
        "tests": [
            "tests/demo/test_studio.py::test_skips_carry_explicit_reasons",
            "tests/demo/test_campaigns.py::test_four_accounts_one_ineligible_fan_out_three_children_and_a_skip",
            "tests/demo/test_campaigns.py::test_child_rejected_by_risk_carries_the_denial_reason",
        ],
        "evidence": [f"{R282}/README.md", f"{R282}/studio-campaign-partial-desktop.png"],
    },
    "AC4": {
        "case": "GIVEN an instrument already owned by an active deployment "
        "THEN a conflicting deployment is rejected with an explanation naming "
        "the owner",
        "tests": [
            "tests/demo/test_campaigns.py::test_conflicting_instrument_is_rejected_naming_the_owner",
            "tests/demo/test_campaigns.py::test_etf_weights_count_as_owned_instruments",
            "tests/demo/test_campaigns.py::test_pending_deployment_owns_until_it_stops",
        ],
        "evidence": [f"{R282}/README.md"],
    },
    "AC5": {
        "case": "GIVEN a campaign where some children fail THEN partial "
        "success is never displayed as campaign success and no fill is "
        "reversed",
        "tests": [
            "tests/demo/test_campaigns.py::test_two_of_four_succeed_is_partial_and_the_fills_stay",
            "tests/demo/test_campaigns.py::test_a_failing_child_never_reverses_its_siblings",
            "tests/demo/test_campaigns.py::test_parent_state_is_derived_and_strict",
            "tests/demo/test_campaigns.py::test_partially_filled_child_blocks_a_succeeded_parent",
            "tests/demo/test_campaigns.py::test_studio_page_shows_campaign_children_and_partial_status",
        ],
        "evidence": [f"{R282}/README.md", f"{R282}/studio-campaign-partial-desktop.png"],
    },
    "AC6": {
        "case": "GIVEN a fleet-breaker halt in tenant A WHEN it is reset from "
        "tenant A THEN tenant B's halt stays in place",
        "blocked": AC6_BLOCKED,
        "tests": [
            "tests/strategies/test_deployments_api.py::test_fleet_breaker_halts_every_deployment_in_scope",
            "tests/api/test_fleet_breaker_tenancy.py::test_reset_in_personal_tenant_cannot_unhalt_tenant_a",
            "tests/api/test_fleet_breaker_tenancy.py::test_trip_is_scoped_one_tenant_halt_does_not_cross",
            "tests/api/test_fleet_breaker_tenancy.py::test_fleet_state_endpoint_reports_active_tenant_row",
        ],
        "evidence": ["origin/feat/alg-3099-a03-tenant-auth @ db6f400"],
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


def totals(junit: Path) -> str:
    suite = ET.parse(junit).getroot()
    if suite.tag == "testsuites":
        inner = suite.find("testsuite")
        suite = inner if inner is not None else suite
    attrs = {k: suite.get(k, "0") for k in ("tests", "failures", "errors", "skipped")}
    return (
        f"{attrs['tests']} tests, {attrs['failures']} failures, "
        f"{attrs['errors']} errors, {attrs['skipped']} skipped"
    )


def verdicts(res: dict[str, tuple[str, str]]) -> dict[str, dict]:
    report = {}
    junit_rel = "artifacts/A11/test-results/junit.xml"
    for ac, spec in CASES.items():
        tests = {t: res.get(t, ("missing", "not collected on main")) for t in spec["tests"]}
        failed = [t for t, (o, _) in tests.items() if o == "failed"]
        skipped = {t: d for t, (o, d) in tests.items() if o == "skipped"}
        if failed:
            status, note = "FAIL", f"failing: {failed}"
        elif spec.get("blocked"):
            status, note = "BLOCKED", spec["blocked"]
        elif skipped:
            status, note = "BLOCKED", f"not run: {skipped}"
        elif any(o == "missing" for o, _ in tests.values()):
            status, note = "BLOCKED", (
                f"not collected: {[t for t, (o, _) in tests.items() if o == 'missing']}"
            )
        else:
            status, note = "PASS", f"{len(tests)} tests passed"
        report[ac] = {
            "status": status,
            "case": spec["case"],
            "note": note,
            "tests": {t: o for t, (o, _) in tests.items()},
            "evidence": [junit_rel, *spec["evidence"]],
        }
    return report


def main(argv: list[str]) -> int:
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A11/test-results/junit.xml"
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
                "packet": "A11",
                "slice": "A11-4 evidence packet (ALG-3283)",
                "tested_commit": tested_commit,
                "command": "make verify-A11",
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )
    lines = [f"make verify-A11 @ {tested_commit} — {totals(junit)}"]
    for ac, v in cases.items():
        lines.append(f"{ac}: {v['status']} — {v['note']}")
    SUMMARY.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if any(v["status"] == "FAIL" for v in cases.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
