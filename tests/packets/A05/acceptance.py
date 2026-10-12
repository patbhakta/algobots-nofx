"""Write artifacts/A05/acceptance.json from the A05 junit report (ALG-3101).

Each acceptance case lists the tests that prove it. A case is PASS only when
every listed test ran and passed; a failing test makes it FAIL; a skipped or
missing test makes it PENDING with the reason. No external-environment case is
claimed: everything here runs offline on recorded fixtures.

    python tests/packets/A05/acceptance.py artifacts/A05/test-results/junit.xml
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "artifacts" / "A05" / "acceptance.json"
W = "tests/marketdata"

CASES: dict[str, dict] = {
    "AC1": {
        "case": "GIVEN BTC/USD spot at two venues and a BTC perpetual THEN all "
        "are distinct executable IDs",
        "tests": [
            f"{W}/test_instruments.py::test_btc_spot_two_venues_and_perp_are_distinct_executable_ids",
            f"{W}/test_instruments.py::test_identity_triple_roundtrips_and_rejects_unknown",
            f"{W}/test_instruments.py::test_registry_rejects_duplicate_identity_or_triple",
            f"{W}/test_instruments.py::test_research_symbols_normalize_separately_from_executable_ids",
            f"{W}/test_instruments.py::test_perpetual_swap_is_identity_only_and_fails_closed",
        ],
        "evidence": ["src/algobots/instruments/instruments.json"],
    },
    "AC2": {
        "case": "GIVEN quantities near tick/lot boundaries THEN decimal rounding "
        "matches the configured instrument and residuals are explicit",
        "tests": [
            f"{W}/test_rounding.py::test_equity_price_rounds_to_nearest_cent_with_residual",
            f"{W}/test_rounding.py::test_kraken_tick_coarser_than_coinbase_rounds_differently",
            f"{W}/test_rounding.py::test_share_quantities_round_down_to_whole_lots",
            f"{W}/test_rounding.py::test_btc_satoshi_lot_never_rounds_quantity_up",
            f"{W}/test_rounding.py::test_exact_values_have_zero_residual",
        ],
        "evidence": [],
    },
    "AC3": {
        "case": "GIVEN weekend equities, 24/7 crypto, DST transitions, incomplete "
        "bars, and stale quotes THEN eligibility/freshness results match fixture "
        "expectations",
        "tests": [
            f"{W}/test_calendar_freshness.py::test_weekend_equity_session_closed",
            f"{W}/test_calendar_freshness.py::test_equity_regular_session_boundaries",
            f"{W}/test_calendar_freshness.py::test_dst_transitions_shift_the_utc_mapping_not_the_wall_clock",
            f"{W}/test_calendar_freshness.py::test_crypto_trades_24x7_including_weekends",
            f"{W}/test_calendar_freshness.py::test_open_market_fresh_quote_is_eligible_and_fresh",
            f"{W}/test_calendar_freshness.py::test_weekend_equity_tick_is_fresh_but_not_eligible",
            f"{W}/test_calendar_freshness.py::test_stale_quote_rejected_by_age_and_flag",
            f"{W}/test_calendar_freshness.py::test_no_data_and_unentitled_sources_fail_closed",
            f"{W}/test_bars_features.py::test_incomplete_bar_is_never_emitted",
            f"{W}/test_bars_features.py::test_gap_detection_counts_missing_intervals",
        ],
        "evidence": ["src/algobots/marketdata/fixtures/recordings.jsonl"],
    },
    "AC4": {
        "case": "GIVEN a later-published filing or corrected price WHEN replaying "
        "an earlier as-of time THEN it is unavailable to that decision",
        "tests": [
            f"{W}/test_replay_asof.py::test_correction_unavailable_before_publication",
            f"{W}/test_replay_asof.py::test_later_event_time_never_outruns_its_available_time",
            f"{W}/test_replay_asof.py::test_as_of_view_is_stable_under_replay",
            f"{W}/test_replay_asof.py::test_price_source_precedence_picks_entitled_websocket_over_rest",
            f"{W}/test_replay_asof.py::test_precedence_fails_closed_on_unknown_sources",
            f"{W}/test_replay_asof.py::test_raw_records_retained_for_correction_replay",
        ],
        "evidence": [],
    },
}


def verdicts(junit: Path) -> dict[str, dict]:
    tree = ET.parse(junit)
    outcomes: dict[str, str] = {}
    for case in tree.iter("testcase"):
        classname = case.get("classname", "").replace(".", "/")
        name = f"{classname}::{case.get('name')}"
        if case.find("failure") is not None or case.find("error") is not None:
            outcomes[name] = "FAIL"
        elif case.find("skipped") is not None:
            outcomes[name] = "SKIPPED"
        else:
            outcomes[name] = "PASS"
    report: dict[str, dict] = {}
    for case_id, spec in CASES.items():
        missing = [t for t in spec["tests"] if t not in outcomes]
        failed = [t for t in spec["tests"] if outcomes.get(t) == "FAIL"]
        skipped = [t for t in spec["tests"] if outcomes.get(t) == "SKIPPED"]
        if failed:
            status, detail = "FAIL", {"failed": failed}
        elif skipped or missing:
            status, detail = "PENDING", {"skipped": skipped, "missing": missing}
        else:
            status, detail = "PASS", {}
        report[case_id] = {
            "case": spec["case"],
            "status": status,
            "tests": spec["tests"],
            "evidence": spec["evidence"],
            **detail,
        }
    return report


def main() -> int:
    junit = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "artifacts/A05/test-results/junit.xml"
    report = verdicts(junit)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "packet": "A05",
        "issue": "ALG-3101",
        "suite": junit.name,
        "cases": report,
        "all_pass": all(c["status"] == "PASS" for c in report.values()),
        "external_environment_cases": "BLOCKED (never claimed; recorded fixtures only)",
    }
    OUT.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"{OUT} — all_pass={summary['all_pass']}")
    for case_id, case in report.items():
        print(f"  {case_id}: {case['status']}")
    return 0 if summary["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
