"""A09 acceptance case 2: stationary deterministic grain, texture-off, reduced motion."""

import re
import struct
import zlib

from algobots.dashboard.design import grain
from algobots.dashboard.design.css import stylesheet
from algobots.dashboard.design.storyboard import page
from algobots.dashboard.design.tokens import GRAIN, MOTION_MS

TILE_SHA256 = "ce5f5c978c432a4ec3a77ca6f910f512fda1dcb0580de7ac07bb3c326befed08"


def _block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i + 1 : j]
    raise AssertionError(selector)


def _pixels(png: bytes) -> tuple[int, int, bytes]:
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    w, h, depth, ctype = struct.unpack(">IIBB", png[16:26])
    idat = png[png.index(b"IDAT") + 4 : png.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert depth == 8 and ctype == 0, "8-bit grayscale (monochrome)"
    rows = [raw[r * (w + 1) : (r + 1) * (w + 1)] for r in range(h)]
    assert all(row[0] == 0 for row in rows), "filter type 0"
    return w, h, b"".join(row[1:] for row in rows)


def test_tile_is_small_monochrome_and_deterministic():
    png = grain.tile_png()
    assert grain.tile_sha256() == TILE_SHA256
    grain.tile_png.cache_clear()
    assert grain.tile_png() == png, "same bytes on rebuild"
    w, h, px = _pixels(png)
    assert (w, h) == (GRAIN["tile_px"],) * 2 and w <= 128
    assert len(png) < 16_000
    mean = sum(px) / len(px)
    assert 110 < mean < 145, "balanced noise, no tint or brightness shift"
    assert grain.tile_png(seed=1) != png


def test_grain_layer_is_stationary_and_below_content():
    rule = _block(stylesheet(), "body::before")
    assert "position: fixed" in rule
    assert "z-index: -1" in rule
    assert "pointer-events: none" in rule
    assert "opacity: var(--grain-opacity)" in rule
    assert "animation" not in rule and "transition" not in rule
    assert f"--grain-opacity: {GRAIN['opacity']};" in stylesheet()


def test_grain_is_one_embedded_tile_not_a_runtime_filter():
    html = page("workspace", "good")
    assert html.count("data:image/png;base64,") == 1
    assert "feTurbulence" not in html and "<canvas" not in html
    assert "requestAnimationFrame" not in html


def test_texture_off_removes_grain():
    css = stylesheet()
    assert 'html[data-texture="off"] body::before { display: none; }' in css
    html = page("overview", "good")
    assert 'data-toggle="texture"' in html
    assert "q.get(k)" in html and 'localStorage.setItem("ab-" + k' in html


def test_reduced_motion_and_motion_off_zero_every_duration():
    css = stylesheet()
    media = _block(css, "@media (prefers-reduced-motion: reduce)")
    toggle = _block(css, 'html[data-motion="off"]')
    for name in MOTION_MS:
        assert f"--dur-{name}: 0ms" in media, name
        assert f"--dur-{name}: 0ms" in toggle, name
    stop = "animation: none !important; transition: none !important"
    assert stop in media
    assert f'html[data-motion="off"] *, *::before, *::after {{ {stop}' in css


def test_all_motion_reaches_the_toggles():
    css = stylesheet()
    for decl in re.findall(r"(?:animation|transition):\s*([^;]+);", css):
        if "none !important" in decl:
            continue
        assert "var(--dur-" in decl, f"hard-coded duration: {decl}"
    assert "infinite" not in css, "no constant motion"


def test_motion_freezes_when_feed_is_lost():
    stale = page("workspace", "stale")
    assert "edge pulse" not in stale and "metric updated" not in stale
    assert "Animation frozen: feed disconnected." in stale
    good = page("workspace", "good")
    assert "edge pulse" in good and "metric updated" in good
