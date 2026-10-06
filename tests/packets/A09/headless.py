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


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> list[bytearray]:
    stride, rows, prev = width * bpp, [], bytearray(width * bpp)
    for y in range(height):
        start = y * (stride + 1)
        ftype, line = raw[start], bytearray(raw[start + 1 : start + 1 + stride])
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b, c = prev[i], prev[i - bpp] if i >= bpp else 0
            if ftype == 1:
                line[i] = (line[i] + a) & 0xFF
            elif ftype == 2:
                line[i] = (line[i] + b) & 0xFF
            elif ftype == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif ftype == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        rows.append(line)
        prev = line
    return rows


def png_pixels(path: Path, box: tuple[int, int, int, int]) -> list[tuple[int, int, int]]:
    """RGB pixels inside box (x0, y0, x1, y1) of an 8-bit RGB/RGBA PNG (stdlib only)."""
    import struct
    import zlib

    data = path.read_bytes()
    width, height, depth, ctype = struct.unpack(">IIBB", data[16:26])
    if depth != 8 or ctype not in (2, 6):
        raise ValueError(f"unsupported PNG: depth {depth}, color type {ctype}")
    bpp = 4 if ctype == 6 else 3
    idat, pos = b"", 8
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos : pos + 8])
        if kind == b"IDAT":
            idat += data[pos + 8 : pos + 8 + length]
        pos += 12 + length
    rows = _unfilter(zlib.decompress(idat), width, height, bpp)
    x0, y0, x1, y1 = box
    return [tuple(rows[y][x * bpp : x * bpp + 3]) for y in range(y0, y1) for x in range(x0, x1)]
