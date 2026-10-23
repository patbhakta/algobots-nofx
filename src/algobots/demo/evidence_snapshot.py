#!/usr/bin/env python3
"""Evidence snapshot (ALG-3357): publish a fresh static export of the demo notebook.

The marimo studio is live and always runs fresh, but the shareable static
snapshot (``kalshi_demo_loop_latest.html``) used to be hand-exported and went
stale between runs. This runs on a systemd timer on .243, exports the notebook
headless inside the marimo container, sanity-checks it, and swaps it in
atomically. A failed export NEVER deletes the previous snapshot - published
evidence only moves forward.

Stdlib only, designed for ``python3 -I`` like the watchdog. Always exits 0
(timer stays healthy); the outcome lands in the state JSON for the watchdog
and cron runs to inspect.

Env overrides: SNAPSHOT_CONTAINER, SNAPSHOT_NOTEBOOK, SNAPSHOT_PUBLISHED,
SNAPSHOT_STATE, SNAPSHOT_DIR_HOST (host path of the container notebooks dir).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path

CONTAINER = os.environ.get("SNAPSHOT_CONTAINER", "nautilus-marimo")
NOTEBOOK = os.environ.get("SNAPSHOT_NOTEBOOK", "/home/nautilus/work/notebooks/kalshi_demo_loop.py")
DIR_HOST = Path(os.environ.get("SNAPSHOT_DIR_HOST", "/mnt/funnytree/algobots/notebooks"))
PUBLISHED = Path(os.environ.get("SNAPSHOT_PUBLISHED", str(DIR_HOST / "kalshi_demo_loop_latest.html")))
STATE = Path(os.environ.get("SNAPSHOT_STATE", "/opt/laya/kalshi/evidence_state.json"))

MIN_BYTES = 50_000  # a real export embeds session data; a broken one is small
MARKERS = (b"kalshi", b"marimo_version")  # content sanity: notebook + marimo export
EXPORT_TIMEOUT_S = 300
TMP_NAME = ".kalshi_demo_loop.snap.html"


def validate_snapshot(path: Path) -> tuple[bool, str]:
    """Return (ok, reason). A snapshot must be big enough and look like the notebook."""
    if not path.exists():
        return False, "export file missing"
    size = path.stat().st_size
    if size < MIN_BYTES:
        return False, f"export too small: {size} bytes < {MIN_BYTES}"
    blob = path.read_bytes()
    for marker in MARKERS:
        if marker not in blob:
            return False, f"missing content marker: {marker!r}"
    return True, f"ok ({size} bytes)"


def publish(tmp: Path, published: Path) -> None:
    """Atomically replace the published snapshot with the validated tmp export."""
    os.replace(tmp, published)


def run_export() -> Path:
    """Headless-export the notebook into a tmp file next to the published one."""
    tmp = DIR_HOST / TMP_NAME
    cmd = [
        "docker", "exec", CONTAINER,
        "marimo", "export", "html", NOTEBOOK,
        "-o", f"{NOTEBOOK.rsplit(/, 1)[0]}/{TMP_NAME}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=EXPORT_TIMEOUT_S)
    if proc.returncode != 0:
        raise RuntimeError(
            f"marimo export rc={proc.returncode}: {proc.stderr[-500:] or proc.stdout[-500:]}")
    return tmp


def write_state(ok: bool, detail: str) -> None:
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps({
            "ok": ok, "detail": detail, "ts": time.time(),
        }, indent=2))
    except OSError:
        pass  # state is best-effort; never mask the real outcome


def main() -> int:
    started = time.time()
    tmp_path = DIR_HOST / TMP_NAME
    try:
        tmp = run_export()
        ok, reason = validate_snapshot(tmp)
        if not ok:
            raise RuntimeError(f"snapshot validation failed: {reason}")
        publish(tmp, PUBLISHED)
        write_state(True, f"{reason} in {time.time() - started:.1f}s -> {PUBLISHED.name}")
        print(f"[evidence-snapshot] published {PUBLISHED} ({reason})")
    except Exception as exc:  # noqa: BLE001 - always exit 0, record why
        write_state(False, str(exc))
        print(f"[evidence-snapshot] FAILED (previous snapshot kept): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
