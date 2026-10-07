"""A10 keyboard + mobile journeys: runs keyboard.mjs against a live /demo.

Starts uvicorn on a free port over a synthetic feed (no broker, no live data,
workers off) and drives it with headless Chromium through playwright-core.
Skips, and says why, when node, playwright-core or a Playwright Chromium is
missing. Set A10_NODE_PATH to the directory containing playwright-core.
"""

import glob
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESULTS = ROOT / "artifacts" / "A10" / "test-results"


def _node_path() -> str | None:
    explicit = os.environ.get("A10_NODE_PATH")
    candidates = [explicit] if explicit else []
    candidates += sorted(glob.glob(str(Path.home() / ".npm" / "_npx" / "*" / "node_modules")))
    for path in candidates:
        if path and (Path(path) / "playwright-core").is_dir():
            return path
    return None


def _chromium() -> bool:
    cache = Path.home() / ".cache" / "ms-playwright"
    return bool(glob.glob(str(cache / "chromium-*" / "chrome-linux*" / "chrome")))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    # Fresh timestamps so the feed reads as connected, not stale.
    now = int(time.time()) // 900 * 900
    feed = tmp_path / "observations.jsonl"
    rows = [
        {
            "event": f"E{i}",
            "strike": 1,
            "outcome": i % 2,
            "ts": now - (12 - i) * 900,
            "p": 0.6,
            "conf": 0.1,
            "jev_choice": "up",
            "jev_conf": 0.5,
            "jev_p": 0.6,
        }
        for i in range(12)
    ]
    feed.write_text("\n".join(json.dumps(r) for r in rows))
    env = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    env.update(
        ALGOBOTS_DEMO_FEED_PATH=str(feed),
        ALGOBOTS_DEMO_STATE_DIR=str(tmp_path),
        ALGOBOTS_DEMO_START=time.strftime("%Y-%m-%d", time.gmtime(now - 86400)),
        ALGOBOTS_DEMO_WORKERS_ENABLED="0",
    )
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "algobots.api.main:app", "--port", str(port)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"{base}/demo", timeout=1)
                break
            except OSError:
                time.sleep(0.1)
        else:
            pytest.fail("uvicorn did not serve /demo within 10s")
        yield base
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_keyboard_and_mobile_journeys(server, tmp_path):
    node, node_path = shutil.which("node"), _node_path()
    if not (node and node_path and _chromium()):
        pytest.skip("needs node, playwright-core (A10_NODE_PATH) and a Playwright Chromium")
    run = subprocess.run(
        [node, str(HERE / "keyboard.mjs"), server, str(tmp_path)],
        env={**os.environ, "NODE_PATH": node_path},
        capture_output=True,
        text=True,
        timeout=120,
    )
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "keyboard.txt").write_text(run.stdout)
    assert run.returncode == 0, run.stdout + run.stderr
    assert "keyboard check: all passed" in run.stdout
