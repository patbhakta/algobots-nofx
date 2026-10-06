"""A09 acceptance cases 1-2 in a real browser: no overflow at the four spec sizes,
texture-off and reduced-motion work. Skips (reported) when no headless Chrome exists."""

import pytest
from headless import SIZES, audit, chrome

from algobots.dashboard.design.storyboard import SCREENS
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
