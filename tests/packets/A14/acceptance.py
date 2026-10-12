"""Write artifacts/A14/acceptance.json + test-results/summary.txt (ALG-3320).

Maps the parent spec's AC1-AC5 to executable cases: each AC lists the
end-to-end packet case (tests/packets/A14/test_acceptance.py) plus the unit
lanes that pin its mechanics (tests/knowledge/ingest/). A case is PASS only
when every listed test ran and passed; failing -> FAIL; skipped or not
collected -> BLOCKED with the reason (fail-closed, A08/A11 vocabulary).

    python tests/packets/A14/acceptance.py artifacts/A14/test-results/junit.xml
"""

from __future__ import annotations

import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A14" / "acceptance.json"
SUMMARY = ROOT / "artifacts" / "A14" / "test-results" / "summary.txt"

AC = "tests/packets/A14/test_acceptance.py"

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN an imported vault WHEN it is re-imported unchanged "
        "THEN zero chunks are re-embedded (idempotent, content-keyed writes)",
        "tests": [
            f"{AC}::test_ac1_unchanged_reimport_reembeds_zero_chunks",
            "tests/knowledge/ingest/test_idempotency.py::test_unchanged_reimport_is_zero_work_everywhere",
            "tests/knowledge/ingest/test_idempotency.py::test_edit_flip_only_the_edited_document",
            "tests/knowledge/ingest/test_idempotency.py::test_reregister_same_root_same_source_id",
            "tests/knowledge/ingest/test_indexing.py::test_unchanged_resync_is_zero_index_work",
        ],
        "evidence": ["artifacts/A14/demo-output.txt"],
    },
    "AC2": {
        "case": "GIVEN an imported note WHEN it is renamed THEN document "
        "identity and citations are kept; WHEN its content is edited THEN a "
        "new version is chained on the same identity",
        "tests": [
            f"{AC}::test_ac2_rename_keeps_identity_and_citations_edit_makes_new_version",
            "tests/knowledge/ingest/test_identity.py::test_rename_keeps_document_identity",
            "tests/knowledge/ingest/test_identity.py::test_edit_creates_new_version_same_document",
            "tests/knowledge/ingest/test_identity.py::test_revert_relinks_existing_version_zero_new_work",
            "tests/knowledge/ingest/test_identity.py::test_rename_and_edit_combined_is_a_new_document",
            "tests/knowledge/ingest/test_indexing.py::test_edit_reembeds_only_changed_chunks",
        ],
        "evidence": ["artifacts/A14/demo-output.txt"],
    },
    "AC3": {
        "case": "GIVEN an exposed source WHEN it is deleted (tombstone) or "
        "its ACL is revoked THEN exposure ceases within 60s and removal is "
        "owner-only",
        "tests": [
            f"{AC}::test_ac3_delete_and_acl_revoke_exposure_ceases_within_60s",
            "tests/knowledge/ingest/test_tombstone.py::test_removal_propagation_window_real_timed",
            "tests/knowledge/ingest/test_tombstone.py::test_removal_requires_owner_role",
            "tests/knowledge/ingest/test_tombstone.py::test_removed_source_stays_hidden_from_cache_after_invalidation",
            "tests/knowledge/ingest/test_tombstone.py::test_cache_ttl_sits_inside_propagation_window",
            "tests/knowledge/ingest/test_acl.py::test_revoked_acl_denies_every_role_including_owner",
        ],
        "evidence": ["artifacts/A14/demo-output.txt"],
    },
    "AC4": {
        "case": "GIVEN traversal attempts, escaping symlinks and malformed "
        "notes WHEN the vault is ingested THEN all are rejected within the "
        "source root, quarantined visibly, and no outside byte is ever read",
        "tests": [
            f"{AC}::test_ac4_traversal_symlink_malformed_rejected_within_source_root",
            "tests/knowledge/ingest/test_security.py::test_symlink_escape_rejected_and_outside_bytes_never_read",
            "tests/knowledge/ingest/test_security.py::test_symlinked_directory_escape_rejected",
            "tests/knowledge/ingest/test_security.py::test_dotdot_traversal_rejected",
            "tests/knowledge/ingest/test_security.py::test_nested_traversal_net_rejected",
            "tests/knowledge/ingest/test_security.py::test_malformed_utf8_note_quarantined_no_placeholder",
            "tests/knowledge/ingest/test_security.py::test_bad_frontmatter_line_quarantined",
            "tests/knowledge/ingest/test_quarantine_surface.py::test_failed_doc_is_queryable_with_visible_error",
        ],
        "evidence": ["artifacts/A14/demo-output.txt"],
    },
    "AC5": {
        "case": "GIVEN an asset whose extraction fails or has no approved "
        "processor THEN the failure is reported and visible; no invented "
        "text is ever substituted",
        "tests": [
            f"{AC}::test_ac5_failed_extraction_reported_no_invented_text",
            "tests/knowledge/ingest/test_assets.py::test_processor_failure_recorded_never_substituted",
            "tests/knowledge/ingest/test_assets.py::test_no_approved_processor_stays_visible",
            "tests/knowledge/ingest/test_assets.py::test_unknown_type_queued_unsupported_never_routed",
            "tests/knowledge/ingest/test_quarantine_surface.py::test_unsupported_asset_surfaces_as_failure",
            "tests/knowledge/ingest/test_parsing.py::test_failed_parse_surfaces_error_and_generates_no_chunks",
        ],
        "evidence": ["artifacts/A14/demo-output.txt"],
    },
}


def results(junit: Path) -> dict[str, tuple[str, str]]:
    """node id (path::name, params folded) -> (outcome, detail); worst wins."""
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
    junit_rel = "artifacts/A14/test-results/junit.xml"
    for ac, spec in CASES.items():
        tests = {t: res.get(t, ("missing", "not collected")) for t in spec["tests"]}
        failed = [t for t, (o, _) in tests.items() if o == "failed"]
        skipped = {t: d for t, (o, d) in tests.items() if o == "skipped"}
        if failed:
            status, note = "FAIL", f"failing: {failed}"
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
    junit = Path(argv[1]) if len(argv) > 1 else ROOT / "artifacts" / "A14" / "test-results" / "junit.xml"
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
                "packet": "A14",
                "slice": "A14-3 flow + acceptance + demo (ALG-3320)",
                "tested_commit": tested_commit,
                "command": "make verify-A14",
                "cases": cases,
            },
            indent=2,
        )
        + "\n"
    )
    lines = [f"make verify-A14 @ {tested_commit} — {totals(junit)}"]
    for ac, v in cases.items():
        lines.append(f"{ac}: {v['status']} — {v['note']}")
    SUMMARY.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 1 if any(v["status"] == "FAIL" for v in cases.values()) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
