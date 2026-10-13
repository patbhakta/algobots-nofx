"""A09 NoFX tokens: /demo palette verbatim, WCAG AA on dark surfaces, no effect tokens."""

import re
from pathlib import Path

import pytest

from algobots.dashboard.design import tokens as t
from algobots.dashboard.design.css import stylesheet

ROOT = Path(__file__).resolve().parents[3]
DASHBOARD_SRC = ROOT / "src" / "algobots" / "dashboard"

# The /demo NoFX theme (src/algobots/demo/theme.py), verbatim.
SPEC_TABLE = {
    "bg": "#0a0d10",
    "panel": "#0f1418",
    "raised": "#151b21",
    "ink": "#d6dde4",
    "muted": "#7c8794",
    "rule-faint": "#1d252d",
    "rule-strong": "#2b3540",
    "positive": "#2ecc71",
    "negative": "#ff5c5c",
    "attention": "#e0a33a",
    "focus": "#5aa9ff",
}


def test_demo_values_recorded_verbatim():
    assert dict(t.SPEC_COLORS) == SPEC_TABLE


def test_shipped_colors_differ_from_spec_only_where_recorded():
    changed = {k for k in SPEC_TABLE if t.COLORS[k].lower() != SPEC_TABLE[k].lower()}
    assert changed == set(t.ADJUSTMENTS)
    surfaces = {"bg", "panel", "raised", "ink", "muted", "rule-faint", "rule-strong"}
    assert surfaces.isdisjoint(changed)


def test_each_adjustment_is_needed_and_minimal():
    for name in sorted(t.ADJUSTMENTS):
        spec, shipped = SPEC_TABLE[name], t.COLORS[name]
        worst_spec = min(t.contrast(spec, t.COLORS[s]) for s in t.SURFACES)
        assert worst_spec < 4.5, f"{name}: spec value already passes AA; adjustment not needed"
        worst_new = min(t.contrast(shipped, t.COLORS[s]) for s in t.SURFACES)
        assert 4.5 <= worst_new < 4.8, f"{name}: {worst_new:.2f} (clear AA by a small margin)"
        on_bg = t.contrast(shipped, t.COLORS["bg"])
        assert on_bg >= 4.5, f"{name}: measured ratio must be recorded"


def test_all_demo_text_values_already_pass_aa_so_nothing_is_adjusted():
    """Measured: every /demo text token clears AA on every dark surface."""
    assert dict(t.ADJUSTMENTS) == {}, "adjustments must carry a measured failing ratio"
    for name in t.TEXT:
        for s in t.SURFACES:
            assert t.contrast(SPEC_TABLE[name], t.COLORS[s]) >= 4.5


@pytest.mark.parametrize("surface", t.SURFACES)
@pytest.mark.parametrize("fg", t.TEXT)
def test_text_meets_wcag_aa_on_dark(fg, surface):
    ratio = t.contrast(t.COLORS[fg], t.COLORS[surface])
    assert ratio >= 4.5, f"{fg} on {surface}: {ratio:.2f}:1"


@pytest.mark.parametrize("surface", t.SURFACES)
@pytest.mark.parametrize("fg", t.NON_TEXT)
def test_focus_ring_meets_non_text_contrast(fg, surface):
    assert t.contrast(t.COLORS[fg], t.COLORS[surface]) >= 3.0


def test_contrast_report_matches_tests():
    rows = t.contrast_report()
    assert len(rows) == len(t.TEXT) * len(t.SURFACES)
    assert all(r["aa_text"] for r in rows)
    assert min(r["ratio"] for r in rows) == pytest.approx(4.75)  # muted on raised, measured


def test_known_contrast_values():
    assert t.contrast("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert t.contrast(t.COLORS["ink"], t.COLORS["bg"]) == pytest.approx(14.21, abs=0.01)


def test_type_is_mono_first_from_the_demo_stack():
    assert t.TYPE["mono"].startswith("ui-monospace")
    assert "JetBrains Mono" in t.TYPE["mono"] and "Menlo" in t.TYPE["mono"]
    assert t.TYPE["body_px"] == 12.5  # /demo body
    assert t.TYPE["meta_px"] == 11.5  # /demo disclosure line
    assert t.TYPE["headline_px"] == 17  # /demo metric value
    assert t.TYPE["line_height"] == 1.45


def test_there_are_no_effect_tokens():
    for gone in ("GRAIN", "MOTION_MS", "SHADOW"):
        assert not hasattr(t, gone), gone
    assert t.RADIUS == "0"
    assert t.RULE_WIDTH == "1px"


def test_tabular_figures_for_financial_values():
    css = stylesheet()
    rule = re.search(r"\.num, table\.data td\.n, \.metric \.value \{([^}]*)\}", css)
    assert rule and "font-variant-numeric: tabular-nums" in rule.group(1)
    assert "tabular-nums lining-nums" in _block(css, "body")


def _block(css: str, selector: str) -> str:
    start = css.index(selector + " {")
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i + 1 : j]
    raise AssertionError(selector)


def test_every_token_is_a_css_custom_property():
    css = stylesheet()
    for name, value in t.COLORS.items():
        assert f"--c-{name}: {value};" in css


def test_surfaces_are_dark():
    for surface in t.SURFACES:
        assert t.luminance(t.COLORS[surface]) < 0.05, surface
    assert t.luminance(t.COLORS["ink"]) > 0.5


def test_stylesheet_declares_dark_color_scheme():
    assert "color-scheme: dark" in stylesheet()


def test_no_hard_coded_colors_outside_tokens():
    for path in DASHBOARD_SRC.rglob("*.py"):
        text = path.read_text()
        for hex_color in re.findall(r"#[0-9A-Fa-f]{6}\b", text):
            if path.name != "tokens.py":
                pytest.fail(f"{path}: hard-coded color {hex_color}; use design tokens")
