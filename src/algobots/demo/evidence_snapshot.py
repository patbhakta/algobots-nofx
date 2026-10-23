#!/usr/bin/env python3
"""Evidence snapshot (ALG-3357): publish a fresh static export of the demo notebook.

The marimo studio is live and always runs fresh, but the shareable static
snapshot (``kalshi_demo_loop_latest.html``) used to be hand-exported and went
stale between runs. This runs on a systemd timer on .243, exports the notebook
headless inside the marimo container, sanity-checks it, and swaps it in
atomically. A failed export NEVER deletes the previous snapshot - published
evidence only moves forward.

The snapshot is published twice: once next to the notebook (container-visible)
and once into the static share-out dir that the ``static-shares`` container
serves at :8203 - that copy is what humans actually open. After publishing, the
script verifies the share URL over HTTP (200 + size floor); an unreachable
snapshot is recorded as a failure in the state JSON so the watchdog sees it.

Stdlib only, designed for ``python3 -I`` like the watchdog. Always exits 0
(timer stays healthy); the outcome lands in the state JSON for the watchdog
and cron runs to inspect.

Env overrides: SNAPSHOT_CONTAINER, SNAPSHOT_NOTEBOOK_DIR, SNAPSHOT_NOTEBOOK,
SNAPSHOT_PUBLISHED, SNAPSHOT_STATE, SNAPSHOT_DIR_HOST (host path of the
container notebooks dir), SNAPSHOT_SHARE_DIR (static share-out dir on the
host), SNAPSHOT_SHARE_URL (URL the share-out is served at).
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

CONTAINER = os.environ.get("SNAPSHOT_CONTAINER", "nautilus-marimo")
NOTEBOOK_DIR = os.environ.get("SNAPSHOT_NOTEBOOK_DIR", "/home/nautilus/work/notebooks")
NOTEBOOK = os.environ.get("SNAPSHOT_NOTEBOOK", NOTEBOOK_DIR + "/kalshi_demo_loop.py")
DIR_HOST = Path(os.environ.get("SNAPSHOT_DIR_HOST", "/mnt/funnytree/algobots/notebooks"))
PUBLISHED = Path(
    os.environ.get("SNAPSHOT_PUBLISHED", str(DIR_HOST / "kalshi_demo_loop_latest.html"))
)
STATE = Path(os.environ.get("SNAPSHOT_STATE", "/opt/laya/kalshi/evidence_state.json"))
SHARE_DIR = Path(os.environ.get("SNAPSHOT_SHARE_DIR", "/mnt/funnytree/algobots/share-out"))
SHARE_PUBLISHED = Path(os.environ.get("SNAPSHOT_SHARE_PUBLISHED", str(SHARE_DIR / PUBLISHED.name)))
SHARE_URL = os.environ.get("SNAPSHOT_SHARE_URL", "http://100.82.57.72:8203/" + PUBLISHED.name)

MIN_BYTES = 50_000  # a real export embeds session data; a broken one is small
MARKERS = (b"kalshi", b"marimo_version")  # content sanity: notebook + marimo export
EXPORT_TIMEOUT_S = 300
HTTP_TIMEOUT_S = 10
TMP_NAME = ".kalshi_demo_loop.snap.html"
TMP_WEB_NAME = ".kalshi_demo_loop.web.html"


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


def publish_web(source: Path, target: Path) -> None:
    """Copy the validated snapshot into the web-served share-out dir, atomically.

    Copy-then-replace (not os.replace) because source and target may live on
    different mounts; the source snapshot stays put for the container.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.parent / TMP_WEB_NAME
    tmp.write_bytes(source.read_bytes())
    os.replace(tmp, target)


def verify_http() -> tuple[bool, str]:
    """Fetch the share URL and confirm the snapshot is actually reachable."""
    req = urllib.request.Request(SHARE_URL, headers={"User-Agent": "evidence-snapshot/1"})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            body = resp.read()
    except Exception as exc:  # noqa: BLE001 - any transport error is a fail
        return False, f"share url unreachable: {exc}"
    if len(body) < MIN_BYTES:
        return False, f"share url served short body: {len(body)} bytes < {MIN_BYTES}"
    return True, f"share url 200 ({len(body)} bytes)"


def run_export() -> Path:
    """Headless-export the notebook into a tmp file next to the published one."""
    tmp = DIR_HOST / TMP_NAME
    cmd = [
        "docker", "exec", CONTAINER,
        "marimo", "export", "html", NOTEBOOK,
        "-o", NOTEBOOK_DIR + "/" + TMP_NAME,
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
    try:
        tmp = run_export()
        ok, reason = validate_snapshot(tmp)
        if not ok:
            raise RuntimeError(f"snapshot validation failed: {reason}")
        publish(tmp, PUBLISHED)
        publish_web(PUBLISHED, SHARE_PUBLISHED)
        web_ok, web_reason = verify_http()
        if web_ok:
            elapsed = time.time() - started
            write_state(True, f"{reason} in {elapsed:.1f}s -> {PUBLISHED.name}; {web_reason}")
        else:
            # Files are fresh but nobody can open them - that is a failure the
            # watchdog must see, not a silent success.
            write_state(False, f"published but NOT reachable: {web_reason}")
        print(f"[evidence-snapshot] published {PUBLISHED} ({reason}); {web_reason}")
    except Exception as exc:  # noqa: BLE001 - always exit 0, record why
        write_state(False, str(exc))
        print(f"[evidence-snapshot] FAILED (previous snapshot kept): {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
