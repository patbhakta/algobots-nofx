"""Demo kill switch: one JSON file, append-only history of every flip."""

from __future__ import annotations

import json
import time
from pathlib import Path


def _path(state_dir: str) -> Path:
    return Path(state_dir) / "kill-switch.json"


def read(state_dir: str) -> dict:
    p = _path(state_dir)
    if not p.exists():
        return {"engaged": False, "since_ts": None, "history": []}
    return json.loads(p.read_text())


def set_engaged(state_dir: str, engaged: bool, *, actor: str, now: float | None = None) -> dict:
    state = read(state_dir)
    if state["engaged"] == engaged:
        return state
    ts = time.time() if now is None else now
    state["engaged"], state["since_ts"] = engaged, ts if engaged else None
    state["history"].append({"engaged": engaged, "ts": ts, "actor": actor})
    p = _path(state_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state))
    tmp.replace(p)
    return state
