"""A09 NoFX guard (ALG-3336): the built sheet and pages ship no effects at all.

Asserts the simplicity-first rules on the real build outputs: no @keyframes,
no transition, no animation, no grain/texture data-URI, no radius/shadow/
gradient flourishes in the CSS; and no texture/motion toggles, localStorage
handling or data-URIs in the built pages.
"""

import re

from algobots.dashboard.design.css import stylesheet
from algobots.dashboard.design.storyboard import pages

BANNED_CSS = (
    "@keyframes",
    "transition",
    "animation",
    "data:image",  # grain/texture tiles
    "box-shadow",
    "text-shadow",
    "border-radius",
    "gradient",
    "filter",
    "backdrop-filter",
    "will-change",
    "perspective",
    "prefers-reduced-motion",  # nothing moves; there is nothing to reduce
)

BANNED_HTML = (
    "data:image",
    "data-toggle",
    "data-texture",
    "data-motion",
    "localStorage",
    "requestAnimationFrame",
    "<canvas",
    "feTurbulence",
    "@keyframes",
    "transition",
    "animation",
)


def test_built_css_has_no_effects():
    css = stylesheet()
    for banned in BANNED_CSS:
        assert banned not in css, banned
    # a duration/grain/shadow variable would be a leftover effect hook
    assert not re.search(r"--dur-|--grain|--shadow", css)


def test_built_css_rules_use_flat_backgrounds():
    css = stylesheet()
    for decl in re.finditer(r"background(?:-image|-color)?:\s*([^;]+);", css):
        value = decl.group(1)
        assert "url(" not in value, decl.group(0)
        assert "linear-" not in value and "radial-" not in value, decl.group(0)


def test_built_pages_expose_no_toggles_or_effects():
    built = pages()
    assert len(built) == 21
    for name, html in built.items():
        for banned in BANNED_HTML:
            assert banned not in html, f"{name}: {banned}"
        assert "<script>" in html, f"{name}: the ?audit=1 script must survive"


def test_audit_script_survives_without_effect_fields():
    html = pages()["overview-good.html"]
    assert 'q.get("audit") === "1"' in html
    assert "scrollWidth" in html and "overflowing" in html and "clipped" in html
    for gone in ("grainDisplay", "reducedDuration", "dataset.texture", "dataset.motion"):
        assert gone not in html, gone


def test_design_module_exports_no_grain_or_motion():
    import algobots.dashboard.design as design
    from algobots.dashboard.design import css, storyboard, tokens

    for module in (design, css, storyboard, tokens):
        for gone in ("grain", "GRAIN", "MOTION_MS", "MOTION", "tile_data_uri", "tile_png"):
            assert not hasattr(module, gone), f"{module.__name__}.{gone}"
