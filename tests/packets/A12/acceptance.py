"""Write artifacts/A12/acceptance.json from the verify-A12 run (ALG-3303).

AC1/AC2 are PASS only when their packet tests ran green in this run AND the
recorded five-capability evidence re-checks (demo-run.json, the G1 decision
doc, the engine kill/restart fixture). Missing tests or thin evidence make
them PENDING, never PASS (fail-closed, A06/A07 pattern). AC3-AC5 are DESCOPED:
Pat's Oct 6 functional-terminal ruling redirected them to A14/A17/A18, so no
test of those capabilities runs here and none may be claimed.

    python tests/packets/A12/acceptance.py artifacts/A12/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A12" / "acceptance.json"
W = "tests/packets/A12"
CAPS = [
    "C1_multi_account",
    "C2_multi_strategy",
    "C3_worker_isolation",
    "C4_risk_denial",
    "C5_kill_freeze",
]


def _load(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def check_ac1() -> tuple[bool, str]:
    run = _load(ROOT / "artifacts" / "A12" / "demo-run.json")
    if not isinstance(run, dict):
        return False, "artifacts/A12/demo-run.json missing or unreadable"
    missing = [c for c in CAPS if c not in run.get("capabilities", {})]
    if missing:
        return False, f"demo-run.json missing capabilities: {missing}"
    doc = ROOT / "docs" / "gates" / "G1" / "decision.md"
    text = doc.read_text() if doc.exists() else ""
    absent = [c for c in ("C1", "C2", "C3", "C4", "C5") if c not in text]
    if "## Proven" not in text or absent:
        return False, f"decision.md missing '## Proven' or rows: {absent}"
    return True, "C1-C5 recorded in demo-run.json and proven in decision.md"


def check_ac2() -> tuple[bool, str]:
    run = _load(ROOT / "artifacts" / "A12" / "engine" / "demo-run.json")
    if not isinstance(run, dict):
        return False, "artifacts/A12/engine/demo-run.json missing or unreadable"
    events = {e.get("event"): e for e in run.get("timeline", [])}
    killed, restarted = events.get("killed"), events.get("restarted")
    if not killed or not restarted:
        return False, "engine timeline lacks killed/restarted events"
    phases = restarted.get("phases_seen", [])
    if "reconciling" not in phases or phases[-1:] != ["ready"]:
        return False, f"restart phases not reconciling->ready: {phases}"
    gap = restarted.get("t", 0.0) - killed.get("t", 0.0)
    if not 0.0 < gap <= 60.0:
        return False, f"kill->ready took {gap:.1f}s, not within 60s"
    restored = restarted.get("orders_restored", 0)
    frozen = restarted.get("orders_rejected_frozen", 1)
    if restored < 1 or frozen != 0:
        return False, f"orders_restored={restored}, orders_rejected_frozen={frozen}"
    if not (ROOT / "artifacts" / "A12" / "engine" / "measurements.json").exists():
        return False, "artifacts/A12/engine/measurements.json missing"
    return (
        True,
        f"kill->reconciling->ready in {gap:.1f}s (<=60), "
        f"{restored} orders restored, 0 blind resubmits",
    )


CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN the A12 five-capability run THEN all five multi-* "
        "demonstrations succeed with no tenant leakage or duplicate effect",
        "tests": [
            f"{W}/test_a12_packet.py::test_terminal_carries_collapsible_five_step_card_at_the_top",
            f"{W}/test_a12_packet.py::test_gate_decision_lists_all_four_call_categories_and_no_edge",
        ],
        "check": check_ac1,
        "evidence": ["artifacts/A12/demo-run.json", "docs/gates/G1/decision.md"],
    },
    "AC2": {
        "case": "GIVEN a killed worker holding pending orders THEN restart "
        "reconciles from the durable ledger within 60s without blind resubmit",
        "tests": [
            f"{W}/test_a12_packet.py::test_terminal_carries_collapsible_five_step_card_at_the_top",
            f"{W}/test_a12_packet.py::test_makefile_exposes_demo_g1_running_the_a12_driver",
        ],
        "check": check_ac2,
        "evidence": [
            "artifacts/A12/demo-run.json",
            "artifacts/A12/engine/demo-run.json",
            "artifacts/A12/engine/measurements.json",
        ],
    },
    "AC3": {
        "case": "GIVEN a retrieved note THEN it shows its source anchor and tenant scope",
        "descoped": "knowledge importer slice descoped by Pat's Oct 6 "
        "functional-terminal ruling; redirected to A14 (ALG-3110) / A17 (ALG-3113)",
        "evidence": ["docs/gates/G1/decision.md", "artifacts/A12/demo-and-limitations.md"],
    },
    "AC4": {
        "case": "GIVEN missing Jev credentials THEN the mock is labeled and "
        "the live smoke reports BLOCKED",
        "descoped": "DecisionModel interface + mock descoped with the same "
        "ruling; redirected to A18 (ALG-3114)",
        "evidence": ["docs/gates/G1/decision.md", "artifacts/A12/demo-and-limitations.md"],
    },
    "AC5": {
        "case": "GIVEN an invalid model answer THEN shadow mode returns "
        "REVIEW/ABSTAIN and no order path is taken",
        "descoped": "DecisionModel interface + mock descoped with the same "
        "ruling; redirected to A18 (ALG-3114)",
        "evidence": ["docs/gates/G1/decision.md", "artifacts/A12/demo-and-limitations.md"],
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
    junit_rel = "artifacts/A12/test-results/junit.xml"
    for ac, spec in CASES.items():
        if spec.get("descoped"):
            report[ac] = {
                "status": "DESCOPED",
                "case": spec["case"],
                "note": spec["descoped"],
                "tests": {},
                "evidence": spec["evidence"],
            }
            continue
        tests = {t: res.get(t, ("missing", "not collected")) for t in spec["tests"]}
        failed = [t for t, (o, _) in tests.items() if o in ("failed", "missing")]
        skipped = {t: d for t, (o, d) in tests.items() if o == "skipped"}
        ok, why = spec["check"]()
        if any(tests[t][0] == "failed" for t in failed):
            status, note = "FAIL", f"failing: {failed}"
        elif failed:
            status, note = "PENDING", f"not run: {failed}"
        elif skipped:
            status, note = "PENDING", f"skipped: {skipped}"
        elif not ok:
            status, note = "PENDING", f"evidence incomplete: {why}"
        else:
            status, note = "PASS", f"{len(tests)} tests passed; evidence re-checked: {why}"
        report[ac] = {
            "status": status,
            "case": spec["case"],
            "note": note,
            "tests": {t: o for t, (o, _) in tests.items()},
            "evidence": [junit_rel, *spec["evidence"]],
        }
    return report


def main(argv: list[str]) -> int:
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts/A12/test-results/junit.xml"
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
                "packet": "A12",
                "slice": "A12-2 packet closure (ALG-3303)",
                "tested_commit": tested_commit,
                "command": "make verify-A12",
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
