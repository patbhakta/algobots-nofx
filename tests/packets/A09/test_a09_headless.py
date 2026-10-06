"""A09 acceptance cases 1-2 in a real browser: no overflow at the four spec sizes,
texture-off and reduced-motion work. Skips (reported) when no headless Chrome exists."""

import pytest
from headless import SIZES, audit, chrome, png_pixels, screenshot

from algobots.dashboard.design.storyboard import SCREENS
from algobots.dashboard.design.tokens import COLORS, GRAIN, rgb
from algobots.dashboard.fixtures import STATES

pytestmark = pytest.mark.skipif(
    chrome() is None, reason="no headless Chrome/Chromium (set A09_CHROME)"
)


@pytest.mark.parametrize("size", SIZES)
@pytest.mark.parametrize("screen", SCREENS)
def test_no_horizontal_overflow_at_spec_sizes(screen, size):
    for state in STATES:
        result = audit(f"{screen}-{state}.html", SIZES[size])
        assert result["overflowing"] == [], (state, result)
        assert result["clipped"] == [], (state, result)  # content wider than its own cell
        assert result["scrollWidth"] <= result["innerWidth"], (state, result)


def test_grain_on_by_default_and_texture_off_hides_it():
    assert audit("workspace-good.html", SIZES["1440x900"])["grainDisplay"] == "block"
    off = audit("workspace-good.html", SIZES["1440x900"], texture="off")
    assert off["texture"] == "off" and off["grainDisplay"] == "none"


def test_motion_off_toggle_and_os_reduced_motion():
    assert audit("overview-good.html", SIZES["390x844"])["reducedDuration"] == "200ms"
    assert audit("overview-good.html", SIZES["390x844"], motion="off")["reducedDuration"] == "0ms"
    assert (
        audit("overview-good.html", SIZES["390x844"], reduced_motion=True)["reducedDuration"]
        == "0ms"
    )


def test_grain_is_actually_painted_and_texture_off_removes_it(tmp_path):
    """Pixel check on paper inside the body box (main's left gutter, below the
    nav, on a page taller than the viewport): the grain must be visible, stay
    within GRAIN opacity of paper, and vanish when texture is off."""
    paper = rgb(COLORS["paper"])
    page, size, box = "workspace-good.html", SIZES["1440x900"], (1, 220, 14, 890)
    on = png_pixels(screenshot(page, size, tmp_path / "on.png"), box)
    off = png_pixels(screenshot(page, size, tmp_path / "off.png", texture="off"), box)
    assert set(off) == {paper}, "texture off must leave plain paper"
    # 3% monochrome noise over paper spans ~8 grey steps per channel.
    assert len(set(on)) >= 6, f"grain not painted: {len(set(on))} distinct colors"
    limit = round(GRAIN["opacity"] * 255) + 1
    assert all(abs(p - q) <= limit for px in on for p, q in zip(px, paper, strict=True))
    shifts = [sum(px) - sum(paper) for px in on]
    assert min(shifts) <= -15 and max(shifts) >= 0, "both grain extremes must appear"
