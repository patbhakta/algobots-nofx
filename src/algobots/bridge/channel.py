"""The shared bridge file channel (ALG-3340): intents in, OrderFilled out.

One directory (mounted into the NoFX and Nautilus containers and the control
plane; see ``docs/bridge.md`` and the stack's ``BRIDGE.md``):

    bridge/
      intents/<intent_id>.json           admitted intents, newest from the API
      processing/<account>/<id>.json     claimed by that account's worker
      done/<intent_id>.json              terminal outcome (filled / rejected)
      fills/<account>.jsonl              Nautilus OrderFilled events, one per line

Lifecycle (at-least-once, idempotent consumers): the control-plane API
admits an intent and writes it under ``intents/``. A paper worker claims it
with an atomic rename into ``processing/<account>/`` — a claim that survives
a crash is replayed on the next drain, so a fill can be written twice; fill
records carry ``intent_id`` and the NoFX view dedupes on it. The terminal
outcome lands in ``done/`` with the fill reference (or the rejection
reason), which is what the status endpoint reads.

Stdlib only: the API process imports this without importing Nautilus.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path

INTENTS = "intents"
PROCESSING = "processing"
DONE = "done"
FILLS = "fills"

_SYMBOL_RE = re.compile(r"^(.+)-((?i:yes|no))$")


class BridgeError(Exception):
    """A typed channel failure (bad layout, malformed intent, missing file)."""


def now_id(ts: float | None = None, prefix: str = "it") -> str:
    """A UTC-sortable unique id: ``it-20261013T171500123456Z-ab12cd34``."""
    t = datetime.fromtimestamp(ts if ts is not None else _now(), UTC)
    return f"{prefix}-{t.strftime('%Y%m%dT%H%M%S%f')[:-3]}Z-{uuid.uuid4().hex[:8]}"


def _now() -> float:
    import time

    return time.time()


def _atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(payload, sort_keys=True))
    tmp.replace(path)


def write_intent(bridge_dir: Path, intent: dict) -> dict:
    """Persist an admitted intent where workers can see it (atomic write)."""
    _atomic_json(Path(bridge_dir) / INTENTS / f"{intent['intent_id']}.json", intent)
    return intent


def _read(path: Path) -> dict | None:
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    return raw if isinstance(raw, dict) else None


def claim_intents(bridge_dir: Path, account: str) -> tuple[list[dict], list[Path]]:
    """Take every unclaimed intent for ``account``; return (intents, malformed).

    Claim = atomic rename ``intents/<id>.json`` -> ``processing/<account>/<id>.json``.
    Leftovers already in ``processing/<account>/`` (a crash between claim and
    finish) are replayed first — at-least-once; consumers dedupe on intent_id.
    Malformed files are returned unmoved so the caller can reject them once.
    """
    root = Path(bridge_dir)
    pending = root / PROCESSING / account
    pending.mkdir(parents=True, exist_ok=True)

    replayed: list[dict] = []  # claims a previous drain never finished: replay
    for path in sorted(pending.glob("*.json")):
        payload = _read(path)
        if payload is not None:
            replayed.append(payload)

    out: list[dict] = []
    malformed: list[Path] = []
    inbox = root / INTENTS
    if inbox.is_dir():
        for path in sorted(inbox.glob("*.json")):
            payload = _read(path)
            if payload is None:
                malformed.append(path)
                continue
            if payload.get("account") != account:
                continue  # another account's worker owns it
            if not payload.get("intent_id"):
                (root / DONE).mkdir(parents=True, exist_ok=True)
                path.replace(root / DONE / path.name)  # unusable: reject once, never replay
                continue
            try:
                path.replace(pending / path.name)  # the claim: atomic rename
            except OSError:
                continue  # raced with another drain of this account: skip
            out.append(payload)
    return replayed + out, malformed


def reject_malformed(bridge_dir: Path, path: Path, reason: str) -> None:
    """Move an unparseable intent file straight to ``done/`` with the reason."""
    root = Path(bridge_dir)
    (root / DONE).mkdir(parents=True, exist_ok=True)
    try:
        path.replace(root / DONE / path.name)
    except OSError:
        return
    _atomic_json(
        root / DONE / path.name,
        {"intent_id": path.stem, "status": "rejected", "reason": reason},
    )


def finish_intent(bridge_dir: Path, account: str, intent_id: str, outcome: dict) -> None:
    """Record the terminal outcome (filled / rejected) and clear the claim.

    Idempotent: a second call for an already-finished intent is a no-op.
    """
    root = Path(bridge_dir)
    processing = root / PROCESSING / account / f"{intent_id}.json"
    intent = _read(processing)
    if intent is None:
        return  # already finished (replayed fill after a crash)
    merged = {**intent, **outcome}
    _atomic_json(root / DONE / f"{intent_id}.json", merged)
    try:
        processing.unlink()
    except OSError:
        pass


def append_fill(bridge_dir: Path, account: str, record: dict) -> None:
    """Append one Nautilus OrderFilled record to the account's fills JSONL."""
    fills = Path(bridge_dir) / FILLS
    fills.mkdir(parents=True, exist_ok=True)
    path = fills / f"{account}.jsonl"
    with open(fills / f"{account}.lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, sort_keys=True) + "\n")
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def read_fills(bridge_dir: Path, account: str, limit: int = 50) -> list[dict]:
    """The account's most recent fill records, oldest first (unparsed lines skipped)."""
    path = Path(bridge_dir) / FILLS / f"{account}.jsonl"
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        try:
            raw = json.loads(line)
        except ValueError:
            continue
        if isinstance(raw, dict):
            rows.append(raw)
    return rows[-limit:] if limit > 0 else rows


def find_intent(bridge_dir: Path, intent_id: str) -> tuple[str, dict] | None:
    """(state, payload) for an intent id: admitted / processing / done, or None.

    ``state`` is where the file sits; ``payload.status`` is the business state
    once terminal (``filled`` / ``rejected``).
    """
    root = Path(bridge_dir)
    for state, path in (
        ("admitted", root / INTENTS / f"{intent_id}.json"),
        ("done", root / DONE / f"{intent_id}.json"),
    ):
        payload = _read(path)
        if payload is not None:
            return state, payload
    if (root / PROCESSING).is_dir():
        for path in sorted((root / PROCESSING).glob(f"*/{intent_id}.json")):
            payload = _read(path)
            if payload is not None:
                return "processing", payload
    return None


def channel_stats(bridge_dir: Path) -> dict:
    """On-disk traffic counters for the stats endpoint (file counts + last fill)."""
    root = Path(bridge_dir)
    counts = {
        "intents_admitted": _count(root / INTENTS, "*.json"),
        "intents_processing": _count(root / PROCESSING, "*/*.json"),
        "intents_done": _count(root / DONE, "*.json"),
    }
    fills_total, last_fill_ts = 0, None
    if (root / FILLS).is_dir():
        for path in sorted((root / FILLS).glob("*.jsonl")):
            lines = [x for x in path.read_text().splitlines() if x.strip()]
            fills_total += len(lines)
            if lines:
                try:
                    rec = json.loads(lines[-1])
                    ts = rec.get("ts_utc") or rec.get("ts_event")
                    if ts and (last_fill_ts is None or str(ts) > str(last_fill_ts)):
                        last_fill_ts = ts
                except ValueError:
                    continue
    counts["fills_recorded"] = fills_total
    counts["last_fill_ts"] = last_fill_ts
    return counts


def _count(dir_: Path, pattern: str) -> int:
    return len(list(dir_.glob(pattern))) if dir_.is_dir() else 0


def valid_symbol(symbol: str) -> bool:
    """``<event>-<YES|NO>`` (outcome case-insensitive): the contract shape."""
    return bool(_SYMBOL_RE.match(symbol.strip())) if symbol and symbol.strip() else False


__all__ = [
    "DONE",
    "FILLS",
    "INTENTS",
    "PROCESSING",
    "BridgeError",
    "append_fill",
    "channel_stats",
    "claim_intents",
    "finish_intent",
    "find_intent",
    "now_id",
    "read_fills",
    "reject_malformed",
    "valid_symbol",
    "write_intent",
]
