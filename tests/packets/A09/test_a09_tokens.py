"""A09 acceptance cases 1-2: spec tokens, WCAG AA with grain on and off, no dark theme."""

import colorsys
import re
from pathlib import Path

import pytest

from algobots.dashboard.design import tokens as t
from algobots.dashboard.design.css import stylesheet

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_SRC = ROOT / "src" / "algobots" / "dashboard"

# DASHBOARD-SPEC "Proposed design tokens" table, verbatim.
SPEC_TABLE = {
    "paper": "#EEE9DD",
    "raised": "#F5F1E8",
    "ink": "#292722",
    "muted": "#686358",
    "rule-strong": "#777064",
    "rule-faint": "#D4CEC1",
    "positive": "#27734E",
    "negative": "#B43732",
    "attention": "#946014",
    "focus": "#346D88",
}


def _hls(hex_color: str) -> tuple[float, float, float]:
    return colorsys.rgb_to_hls(*(c / 255 for c in t.rgb(hex_color)))


def test_spec_values_recorded_verbatim():
    assert dict(t.SPEC_COLORS) == SPEC_TABLE


def test_shipped_colors_differ_from_spec_only_where_recorded():
    changed = {k for k in SPEC_TABLE if t.COLORS[k] != SPEC_TABLE[k]}
    assert changed == set(t.ADJUSTMENTS)
    assert {"paper", "raised", "ink", "muted", "rule-strong", "rule-faint"}.isdisjoint(changed)


@pytest.mark.parametrize("name", sorted(t.ADJUSTMENTS))
def test_each_adjustment_is_needed_and_minimal(name):
    spec, shipped = SPEC_TABLE[name], t.COLORS[name]
    worst_spec = min(t.worst_contrast(spec, t.COLORS[s], grain=True) for s in t.SURFACES)
    assert worst_spec < 4.5, f"{name}: spec value already passes AA; adjustment not justified"
    worst_new = min(t.worst_contrast(shipped, t.COLORS[s], grain=True) for s in t.SURFACES)
    assert 4.5 <= worst_new < 4.8, f"{name}: {worst_new:.2f} (should clear AA by a small margin)"
    (h0, l0, s0), (h1, l1, s1) = _hls(spec), _hls(shipped)
    assert abs(h0 - h1) * 360 < 2.5 and abs(s0 - s1) < 0.03, f"{name}: hue/saturation drifted"
    assert l1 < l0 and l0 - l1 < 0.03, f"{name}: lightness change {l0 - l1:.3f} too large"


@pytest.mark.parametrize("grain", [False, True], ids=["grain-off", "grain-on"])
@pytest.mark.parametrize("surface", t.SURFACES)
@pytest.mark.parametrize("fg", t.TEXT)
def test_text_meets_wcag_aa_on_paper(fg, surface, grain):
    ratio = t.worst_contrast(t.COLORS[fg], t.COLORS[surface], grain)
    assert ratio >= 4.5, f"{fg} on {surface} (grain {'on' if grain else 'off'}): {ratio:.2f}:1"


@pytest.mark.parametrize("surface", t.SURFACES)
@pytest.mark.parametrize("fg", t.NON_TEXT)
def test_ui_boundaries_meet_non_text_contrast(fg, surface):
    assert t.worst_contrast(t.COLORS[fg], t.COLORS[surface], grain=True) >= 3.0


def test_grain_extremes_cover_the_full_tile_range():
    dark, light = t.grain_extremes(t.COLORS["paper"])
    assert t.luminance(dark) < t.luminance(t.COLORS["paper"]) < t.luminance(light)
    assert t.GRAIN["levels"] == (0, 255)


def test_contrast_report_matches_tests():
    rows = t.contrast_report()
    assert len(rows) == len(t.TEXT) * len(t.SURFACES) * 2
    assert all(r["aa_text"] for r in rows)


def test_known_contrast_values():
    assert t.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert t.contrast(SPEC_TABLE["attention"], SPEC_TABLE["paper"]) == pytest.approx(4.40, abs=0.01)


def test_grain_opacity_and_type_sizes_follow_spec():
    assert 0.02 <= t.GRAIN["opacity"] <= 0.04
    assert 14 <= t.TYPE["body_px"] <= 16
    assert 12 <= t.TYPE["meta_px"] <= 13
    assert 22 <= t.TYPE["headline_px"] <= 28
    assert 150 <= t.MOTION_MS["depth"] <= 250
    assert 180 <= t.MOTION_MS["drawer"] <= 240


def test_tabular_figures_for_financial_values():
    css = stylesheet()
    rule = re.search(r"\.num, table\.data td\.n, \.metric \.value \{([^}]*)\}", css)
    assert rule and "font-variant-numeric: tabular-nums" in rule.group(1)


def test_every_token_is_a_css_custom_property():
    css = stylesheet()
    for name, value in t.COLORS.items():
        assert f"--c-{name}: {value};" in css


def test_surfaces_are_light_paper():
    for surface in t.SURFACES:
        assert t.luminance(t.COLORS[surface]) > 0.75, surface


DARK_MARKERS = re.compile(
    r"prefers-color-scheme:\s*dark|data-theme=.dark|theme-dark|\.dark\b|dark-mode|color-scheme:\s*dark",
    re.I,
)


def test_stylesheet_has_no_dark_theme():
    css = stylesheet()
    assert "color-scheme: light" in css
    assert not DARK_MARKERS.search(css)
    for decl in re.finditer(r"background(?:-color)?:\s*([^;]+);", css):
        value = decl.group(1)
        for var in re.findall(r"var\(--c-([a-z-]+)\)", value):
            assert t.luminance(t.COLORS[var]) > 0.05, f"dark background {var}: {decl.group(0)}"
        for hex_color in re.findall(r"#[0-9A-Fa-f]{6}\b", value):
            assert t.luminance(hex_color) > 0.05, decl.group(0)


def test_no_dark_theme_assumption_in_dashboard_sources():
    for path in DASHBOARD_SRC.rglob("*.py"):
        text = path.read_text()
        assert not DARK_MARKERS.search(text), path
        for hex_color in re.findall(r"#[0-9A-Fa-f]{6}\b", text):
            if path.name != "tokens.py":
                pytest.fail(f"{path}: hard-coded color {hex_color}; use design tokens")
