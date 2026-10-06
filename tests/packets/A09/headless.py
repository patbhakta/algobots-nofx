"""Headless Chromium helpers for A09 (screenshots and layout audit).

Uses a locally available Chrome/Chromium binary; nothing is installed. Set
`A09_CHROME` to choose one explicitly; otherwise the Playwright browser cache
and PATH are searched. Pages are opened from disk (`file://`), so no server or
live service is involved.
"""

import glob
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
STORYBOARD = ROOT / "artifacts" / "A09" / "storyboard"
SIZES = {
    "1920x1114": (1920, 1114),
    "1440x900": (1440, 900),
    "1024x768": (1024, 768),
    "390x844": (390, 844),
}
_AUDIT = re.compile(r'<pre id="audit">(.*?)</pre>', re.S)


def chrome() -> str | None:
    explicit = os.environ.get("A09_CHROME")
    if explicit:
        return explicit if Path(explicit).exists() else None
    cache = Path.home() / ".cache" / "ms-playwright"
    for pattern in (
        "chromium_headless_shell-*/chrome-headless-shell-linux64/chrome-headless-shell",
        "chromium-*/chrome-linux*/chrome",
    ):
        found = sorted(glob.glob(str(cache / pattern)), reverse=True)
        if found:
            return found[0]
    for name in ("chrome-headless-shell", "chromium", "chromium-browser", "google-chrome"):
        if shutil.which(name):
            return shutil.which(name)
    return None


def _run(args: list[str], timeout: int = 60) -> str:
    binary = chrome()
    if binary is None:
        raise RuntimeError("no headless Chrome/Chromium found (set A09_CHROME)")
    base = [binary, "--no-sandbox", "--disable-gpu", "--hide-scrollbars", "--no-first-run"]
    return subprocess.run(
        base + args, capture_output=True, text=True, timeout=timeout, check=True
    ).stdout


def url(page: str, **query: str) -> str:
    q = "&".join(f"{k}={v}" for k, v in query.items())
    return (STORYBOARD / page).as_uri() + (f"?{q}" if q else "")


def audit(page: str, size: tuple[int, int], *, reduced_motion: bool = False, **query: str) -> dict:
    flags = [f"--window-size={size[0]},{size[1]}", "--virtual-time-budget=1000", "--dump-dom"]
    if reduced_motion:
        flags.insert(0, "--force-prefers-reduced-motion")
    dom = _run(flags + [url(page, audit="1", **query)])
    match = _AUDIT.search(dom)
    if not match:
        raise RuntimeError(f"audit block missing for {page}")
    return json.loads(match.group(1).replace("&quot;", '"').replace("&amp;", "&"))


def screenshot(page: str, size: tuple[int, int], out: Path, **query: str) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            f"--window-size={size[0]},{size[1]}",
            "--virtual-time-budget=1000",
            f"--screenshot={out}",
            url(page, **query),
        ]
    )
    return out
