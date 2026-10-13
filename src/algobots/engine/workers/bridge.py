"""File-channel mirror for the NoFX<->Nautilus bridge (ALG-3339 ms3 / ALG-3340).

When ``ALGOBOTS_BRIDGE_DIR`` is set (deployed: the ``/opt/algobots-stack/bridge``
volume shared with the NoFX and jupyter containers — see its ``BRIDGE.md``),
the API mirrors every accepted v1 order request to ``intents/intents.jsonl``,
the paper workers mirror every Nautilus ``OrderFilled`` event to
``fills/fills.jsonl``, and the API middleware keeps per-endpoint traffic and
latency counters in ``stats.json`` (OpenAlgo feature pull #6, reference-only
per ADR 0001). Mirroring is observability: a channel write failure must never
reach the trading path, so every failure is swallowed here.

Stdlib only: imported by the API (no Nautilus) and by the workers alike.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
import time
from pathlib import Path

_lock = threading.Lock()


def bridge_dir() -> str:
    """The shared channel root, or ``""`` when mirroring is off."""
    return os.environ.get("ALGOBOTS_BRIDGE_DIR", "")


def _lockfile(p: Path) -> Path:
    return p.with_name(p.name + ".lock")


def _append(rel: str, record: dict) -> None:
    root = bridge_dir()
    if not root:
        return
    p = Path(root) / rel
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(_lockfile(p), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with p.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(record, separators=(",", ":")) + "\n")
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except OSError:
        pass


def mirror_intent(req: dict) -> None:
    """One v1 order request as the API accepted it (the gate journal stays tickets)."""
    _append("intents/intents.jsonl", {"mirrored_ts": time.time(), **req})


def mirror_fill(rec: dict) -> None:
    """One Nautilus ``OrderFilled`` event from an account worker."""
    _append("fills/fills.jsonl", rec)


def bump_stats(endpoint: str, ms: float, code: int) -> None:
    """Traffic + latency counters for one served v1 request."""
    root = bridge_dir()
    if not root:
        return
    p = Path(root) / "stats.json"
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with _lock, open(_lockfile(p), "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                try:
                    stats = json.loads(p.read_text())
                except (OSError, ValueError):
                    stats = {}
                entry = stats.setdefault("calls", {}).setdefault(
                    endpoint, {"count": 0, "total_ms": 0.0, "max_ms": 0.0}
                )
                entry["count"] += 1
                entry["total_ms"] = round(entry["total_ms"] + ms, 3)
                entry["max_ms"] = round(max(entry["max_ms"], ms), 3)
                entry["last_status"] = code
                stats["updated_ts"] = time.time()
                tmp = p.with_suffix(".tmp")
                tmp.write_text(json.dumps(stats))
                tmp.replace(p)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    except OSError:
        pass
