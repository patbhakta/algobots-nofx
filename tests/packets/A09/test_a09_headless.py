"""A09 acceptance in a real browser: no overflow at the four spec sizes.
Skips (reported) when no headless Chrome exists."""

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
        assert result["clipped"] == [], (state, result)  # content wider than its own cell
        assert result["scrollWidth"] <= result["innerWidth"], (state, result)


def test_audit_report_carries_no_effect_fields():
    result = audit("workspace-good.html", SIZES["1440x900"])
    assert set(result) == {"innerWidth", "scrollWidth", "overflowing", "clipped"}
