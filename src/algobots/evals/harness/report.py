"""Report rendering: markdown + JSON with per-band intervals, baselines, and caveats."""

from __future__ import annotations

import json
from collections.abc import Sequence

from .baselines import chance_level
from .records import DecisionRecord, MoneyGateError
from .scoring import HarnessSummary


def enforce_money_gate(records: Sequence[DecisionRecord], gating_money: bool) -> None:
    """Nothing gates money unless every scored decision was preregistered prospectively."""
    if not gating_money:
        return
    unregistered = [r.decision_id for r in records if not r.preregistered_at]
    if unregistered:
        raise MoneyGateError(
            "money-gating runs require preregistered decisions; "
            f"missing preregistered_at on {len(unregistered)} records, e.g. {unregistered[:3]}"
        )


def _fmt(value: float | None, pct: bool = False, digits: int = 4) -> str:
    if value is None:
        return "n/a"
    if pct:
        return f"{value * 100:.{digits - 2}f}%"
    return f"{value:.{digits}f}"


def _verdict(beats_baseline: bool | None) -> str:
    if beats_baseline is None:
        return "n/a"
    return "beats-baseline" if beats_baseline else "at-baseline"


def _certification_block(summary: HarnessSummary) -> list[str]:
    lines: list[str] = []
    lines.append("## Certification vs majority-label baseline")
    lines.append("")
    if summary.baseline_hit_rate is None:
        lines.append("_Insufficient settled cells to compute the majority-label baseline._")
        lines.append("")
        return lines
    rates = ", ".join(
        f"{label}: {_fmt(rate, pct=True)}" for label, rate in summary.base_rates.items()
    )
    lines.append(
        f"- Majority-label baseline hit-rate: {_fmt(summary.baseline_hit_rate, pct=True)} "
        f"(base rates: {rates})"
    )
    if summary.edge_demonstrated is True:
        lines.append(
            "- Verdict: **edge demonstrated** — overall hit-rate Wilson lower bound "
            f"{_fmt(summary.overall.ci_low, pct=True)} clears the baseline "
            f"{_fmt(summary.baseline_hit_rate, pct=True)}. Validate per-band before any gating use."
        )
    elif summary.edge_demonstrated is False:
        lines.append(
            "- Verdict: no edge demonstrated vs baseline "
            "(overall Wilson lower bound at/below the majority-label rate; "
            "expected for known-random controls)."
        )
    else:
        lines.append("- Verdict: insufficient settled cells.")
    lines.append("")
    return lines


def render_markdown(
    summary: HarnessSummary,
    records: Sequence[DecisionRecord],
    baseline_summaries: dict[str, HarnessSummary] | None = None,
    title: str = "Decision-quality report",
    gating_money: bool = False,
) -> str:
    enforce_money_gate(records, gating_money)
    chance = chance_level(summary.bands)
    lines: list[str] = []
    lines.append(f"# {title}")
    lines.append("")
    lines.append(
        f"- Cells scored: {summary.overall.count} (unsettled/pending: {summary.unsettled})"
    )
    lines.append(
        f"- Label definition: explicit flat band ±{_fmt(summary.flat_threshold)}; "
        f"bands {list(summary.bands)}"
    )
    lines.append(f"- Chance level: {_fmt(chance, pct=True)}")
    lines.append("")
    lines.append("## Per-band performance (predicted band -> realized)")
    lines.append("")
    lines.append(
        "| Predicted band | n | Hit rate | Wilson 95% CI | Mean alpha | Mean Brier | Vs baseline |"
    )
    lines.append("| --- | ---: | ---: | --- | ---: | ---: | --- |")
    for band in summary.bands:
        band_score = summary.per_band[band]
        ci = (
            f"[{_fmt(band_score.ci_low, pct=True)}, {_fmt(band_score.ci_high, pct=True)}]"
            if band_score.ci_low is not None
            else "n/a"
        )
        lines.append(
            f"| {band} | {band_score.count} | {_fmt(band_score.hit_rate, pct=True)} "
            f"| {ci} | {_fmt(band_score.mean_alpha, pct=True)} | {_fmt(band_score.mean_brier)} "
            f"| {_verdict(band_score.beats_baseline)} |"
        )
    overall = summary.overall
    overall_ci = (
        f"[{_fmt(overall.ci_low, pct=True)}, {_fmt(overall.ci_high, pct=True)}]"
        if overall.ci_low is not None
        else "n/a"
    )
    lines.append(
        f"| **overall** | {overall.count} | {_fmt(overall.hit_rate, pct=True)} "
        f"| {overall_ci} | {_fmt(overall.mean_alpha, pct=True)} | {_fmt(overall.mean_brier)} "
        f"| {_verdict(overall.beats_baseline)} |"
    )
    lines.append("")
    lines.extend(_certification_block(summary))
    lines.append("## Baselines (identical protocol, mandatory comparison)")
    lines.append("")
    if baseline_summaries:
        lines.append("| Baseline | n | Hit rate | Wilson 95% CI | Brier |")
        lines.append("| --- | ---: | ---: | --- | ---: |")
        lines.append(
            f"| chance (uniform) | {overall.count} | {_fmt(chance, pct=True)} | - | - |"
        )
        for name, base in baseline_summaries.items():
            base_ci = (
                f"[{_fmt(base.overall.ci_low, pct=True)}, {_fmt(base.overall.ci_high, pct=True)}]"
                if base.overall.ci_low is not None
                else "n/a"
            )
            lines.append(
                f"| {name} | {base.overall.count} | {_fmt(base.overall.hit_rate, pct=True)} "
                f"| {base_ci} | {_fmt(base.brier)} |"
            )
        lines.append("")
    else:
        lines.append("_No baselines supplied — a report without baselines is not evidence._")
        lines.append("")
    lines.append("## Model/version pins")
    lines.append("")
    models = sorted({(r.model_name, r.model_revision, r.question_set_revision) for r in records})
    for model_name, model_revision, question_revision in models:
        lines.append(f"- {model_name} @ {model_revision}, question-set {question_revision}")
    if not models:
        lines.append("- (no records)")
    lines.append("")
    lines.append("## Caveats")
    lines.append("")
    lines.append(
        "- Probabilities are model responses, not calibrated win rates; "
        "calibration must be measured prospectively."
    )
    lines.append(
        "- Small samples move materially when the window changes; "
        "Wilson intervals show the uncertainty."
    )
    lines.append("- Retrospective evaluation may be contaminated by model preknowledge of history.")
    gate = (
        "preregistered-only: eligible to gate money"
        if gating_money
        else "not eligible to gate money"
    )
    lines.append(f"- Money gate: {gate}. Only prospective, preregistered runs may gate money.")
    lines.append("")
    return "\n".join(lines)


def render_json(
    summary: HarnessSummary,
    records: Sequence[DecisionRecord],
    baseline_summaries: dict[str, HarnessSummary] | None = None,
    gating_money: bool = False,
) -> str:
    enforce_money_gate(records, gating_money)
    payload = {
        "summary": summary.to_dict(),
        "baselines": {name: base.to_dict() for name, base in (baseline_summaries or {}).items()},
        "chance_level": chance_level(summary.bands),
        "money_gate": {
            "gating_money": gating_money,
            "preregistered": all(bool(r.preregistered_at) for r in records) if records else False,
        },
        "records": [r.to_dict() for r in records],
    }
    return json.dumps(payload, indent=2, sort_keys=True)
