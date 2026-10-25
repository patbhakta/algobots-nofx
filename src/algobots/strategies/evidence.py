"""Publish immutable, self-contained marimo evidence from stored backtest results."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID, uuid4


def evidence_record(result_id: str, result: dict, base_url: str) -> dict:
    identity = str(UUID(result_id))
    return {
        "backtest_row_id": identity,
        "artifact_hash": result["artifact"]["artifact_hash"],
        "snapshot_id": result["dataset"]["snapshot_id"],
        "dataset_sha256": result["dataset"]["sha256"],
        "notebook_url": base_url.rstrip("/")
        + "/?"
        + urlencode({"file": f"evidence/{identity}.py"}),
        "result_sha256": hashlib.sha256(
            json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def notebook_source(result_id: str, result: dict) -> str:
    # repr encodes all source data as a string literal: names cannot become Python code.
    payload = repr(json.dumps({"backtest_row_id": result_id, **result}, sort_keys=True))
    return (
        '''"""Immutable Studio backtest evidence. Generated from a stored result row."""
import marimo
__generated_with = "0.25.1"
app = marimo.App(width="medium")

@app.cell
def _():
    import json
    import marimo as mo
    return json, mo

@app.cell
def _(json):
    result = json.loads('''
        + payload
        + """)
    return (result,)

@app.cell
def _(mo, result):
    mo.vstack([
        mo.md("# Studio backtest evidence"),
        mo.md("Historical simulation; fills and PnL are backtest results."),
        mo.ui.table([{
            "backtest_row_id": result["backtest_row_id"],
            "artifact_hash": result["artifact"]["artifact_hash"],
            "executor": result["executor"],
            **result["metrics"],
        }], selection=None),
    ])
    return

@app.cell
def _(mo, result):
    values = [float(point["equity"]) - float(result["metrics"]["starting_equity"])
              for point in result["equity_curve"]]
    low, high = min(values, default=0), max(values, default=0)
    points = " ".join(
        f"{20 + index * 760 / max(1, len(values) - 1):.2f},"
        f"{280 - (value - low) * 260 / (high - low or 1):.2f}"
        for index, value in enumerate(values)
    )
    chart = mo.Html(
        '<svg viewBox="0 0 800 300" role="img" aria-label="Backtest PnL curve">'
        f'<polyline points="{points}" fill="none" stroke="#2563eb" stroke-width="2"/>'
        '</svg>'
    )
    mo.vstack([
        mo.md(f"## PnL curve — Range: {low:.2f} to {high:.2f}; intervals in replay order."),
        chart,
        mo.ui.table(result["equity_curve"], selection=None),
        mo.md("## Fills"),
        mo.ui.table(result["trades"], selection=None),
    ])
    return

@app.cell
def _(mo, result):
    mo.vstack([
        mo.md("## Data timeline"),
        mo.ui.table([result["dataset"]], selection=None),
        mo.md("## Gaps"),
        mo.ui.table(result.get("data_timeline", {}).get("gaps", []), selection=None),
        mo.md(result.get("data_timeline", {}).get(
            "gap_policy", "Legacy result: gaps were not recorded.")),
    ])
    return

if __name__ == "__main__":
    app.run()
"""
    )


def publish_notebook(root: Path, result_id: str, result: dict, base_url: str) -> dict:
    """Atomic publication; an existing result may never acquire different content."""
    record = evidence_record(result_id, result, base_url)
    directory = root / "evidence"
    directory.mkdir(parents=True, exist_ok=True, mode=0o2770)
    directory.chmod(0o2770)  # UID 1000 needs a writable marimo cache alongside evidence.
    target = directory / f"{UUID(result_id)}.py"
    source = notebook_source(result_id, result).encode()
    if target.exists():
        if target.read_bytes() != source:
            raise ValueError("Stored notebook differs from immutable backtest result")
        return record
    temporary = directory / f".{uuid4()}.py"
    try:
        with temporary.open("xb") as stream:
            stream.write(source)
        os.chmod(temporary, 0o664)
        # link is create-only: racing publishers cannot replace immutable evidence.
        try:
            os.link(temporary, target)
        except FileExistsError:
            if target.read_bytes() != source:
                raise ValueError("Concurrent evidence content mismatch") from None
    finally:
        temporary.unlink(missing_ok=True)
    return record
