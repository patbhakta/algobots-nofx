"""(ticker x trade_date) grid runner with a resumable skip-set checkpoint.

Resume semantics (ported from the stock-vaults harness line, ALG-3086):
completed and no-data-skipped cells are persisted as fsynced JSONL state and
never re-executed; a torn final state line is dropped and truncated so the
cell re-executes cleanly; mid-file corruption raises CorruptStateError so
evidence is never silently dropped. Exceptions remain transient failures:
they are recorded as errors and retried on resume.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from .records import DecisionRecord

EvaluateFn = Callable[[str, str], "DecisionRecord | SkipCell | None"]


class CorruptStateError(Exception):
    """Raised when the checkpoint is undecodable beyond a torn final line."""


@dataclass(frozen=True)
class SkipCell:
    """Returned by an evaluate_fn when a cell cannot produce a decision.

    The skip is persisted so resume never retries it; it never enters scoring
    evidence. Raising an exception instead keeps the cell a transient failure.
    """

    reason: str = "no_data"


@dataclass(frozen=True)
class GridCell:
    ticker: str
    trade_date: str

    def key(self) -> str:
        return f"{self.ticker}@{self.trade_date}"


@dataclass
class GridRunStats:
    cells_total: int = 0
    skipped: int = 0
    executed: int = 0
    errors: int = 0
    plan_only: bool = False
    no_data_skipped: int = 0
    executed_keys: list[str] = field(default_factory=list)
    error_keys: list[str] = field(default_factory=list)
    skip_keys: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cells_total": self.cells_total,
            "skipped": self.skipped,
            "executed": self.executed,
            "errors": self.errors,
            "plan_only": self.plan_only,
            "no_data_skipped": self.no_data_skipped,
            "executed_keys": list(self.executed_keys),
            "error_keys": list(self.error_keys),
            "skip_keys": list(self.skip_keys),
        }


def plan_grid(tickers: Sequence[str], trade_dates: Sequence[str]) -> list[GridCell]:
    """Full (ticker x trade_date) grid in deterministic order."""
    cells = [GridCell(ticker, trade_date) for ticker in tickers for trade_date in trade_dates]
    return cells


def trading_dates_back_from(last_date: str, count: int) -> list[str]:
    """`count` calendar-weekday dates ending at last_date (calendars: S2.1/A05 scope)."""
    end = date.fromisoformat(last_date)
    out: list[str] = []
    cursor = end
    while len(out) < count:
        if cursor.weekday() < 5:
            out.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return list(reversed(out))


def load_checkpoint(path: Path) -> tuple[set[str], list[dict]]:
    """Read completed and no-data-skipped cells from a JSONL checkpoint.

    - Entries with `status: ok` or a persisted skip (`status: skip` or
      `kind: skip`) join the done set: completed cells and permanent no-data
      skips are never re-executed.
    - A torn final line is dropped and the file truncated to the last good
      record so appends rebuild on clean state and the cell re-executes.
    - An undecodable line with content after it raises CorruptStateError:
      mid-file corruption is never silently dropped.
    - Error entries are history only: those cells retry on resume.
    """
    done: set[str] = set()
    lines: list[dict] = []
    if not path.exists():
        return done, lines
    good_bytes = 0
    with path.open("r", encoding="utf-8") as handle:
        while True:
            line = handle.readline()
            if not line:
                good_bytes = handle.tell()
                break
            stripped = line.strip()
            if not stripped:
                good_bytes = handle.tell()
                continue
            try:
                entry = json.loads(stripped)
            except json.JSONDecodeError as error:
                if handle.read().strip():
                    raise CorruptStateError(
                        f"{path}: undecodable entry with content after it at byte {good_bytes}"
                    ) from error
                break
            lines.append(entry)
            status = entry.get("status")
            if status == "ok":
                done.add(str(entry.get("key")))
            elif status == "skip" or entry.get("kind") == "skip":
                key = entry.get("key") or f"{entry.get('ticker')}@{entry.get('date')}"
                done.add(str(key))
            good_bytes = handle.tell()
    if good_bytes < path.stat().st_size:
        with path.open("r+b") as handle:
            handle.truncate(good_bytes)
    return done, lines


def run_grid(
    cells: Sequence[GridCell],
    evaluate_fn: EvaluateFn,
    checkpoint_path: str | Path | None = None,
    plan_only: bool = False,
    max_errors: int | None = None,
) -> tuple[list[DecisionRecord], GridRunStats]:
    """Execute the grid, skipping cells already marked ok or skipped in the checkpoint.

    - One JSONL line per finished cell, written and fsynced immediately: an
      interrupted run resumes by skipping everything already persisted.
    - `evaluate_fn` may return `SkipCell(reason)` or `None` when a cell has no
      data: the skip is persisted (never retried, never scored). Raising an
      exception records a transient error that retries on resume.
    - `plan_only=True` builds the run without calling the model (no spend).
    - Evaluation errors are recorded and counted; `max_errors` stops the run.
    """
    stats = GridRunStats(cells_total=len(cells), plan_only=plan_only)
    path = Path(checkpoint_path) if checkpoint_path else None
    done: set[str] = set()
    if path is not None:
        done, _ = load_checkpoint(path)

    records: list[DecisionRecord] = []

    def append_entry(entry: dict) -> None:
        if path is None:
            return
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

    for cell in cells:
        key = cell.key()
        if key in done:
            stats.skipped += 1
            continue
        if plan_only:
            stats.executed += 1
            stats.executed_keys.append(key)
            append_entry({"key": key, "status": "planned"})
            continue
        try:
            record = evaluate_fn(cell.ticker, cell.trade_date)
        except Exception as exc:  # the harness records the failure and keeps the grid running
            stats.errors += 1
            stats.error_keys.append(key)
            append_entry({"key": key, "status": "error", "error": str(exc)})
            if max_errors is not None and stats.errors >= max_errors:
                break
            continue
        if record is None or isinstance(record, SkipCell):
            reason = record.reason if isinstance(record, SkipCell) else "no_data"
            stats.no_data_skipped += 1
            stats.skip_keys.append(key)
            done.add(key)
            append_entry({"key": key, "kind": "skip", "status": "skip", "reason": reason})
            continue
        stats.executed += 1
        stats.executed_keys.append(key)
        records.append(record)
        append_entry({"key": key, "status": "ok", "decision_id": record.decision_id})
    return records, stats
