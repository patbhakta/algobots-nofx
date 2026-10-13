"""NoFX design tokens (ALG-3336 board directive): flat, dark, effects-free.

Base values are the /demo terminal theme (`src/algobots/demo/theme.py`) kept
verbatim in `SPEC_COLORS`; `COLORS` is what ships. A text token differs from
the /demo value only where it misses WCAG AA (4.5:1) on a dark surface; each
change is a small lightness shift (same hue) with its measured ratio recorded
in `ADJUSTMENTS`. Every /demo text value already clears AA on bg, panel and
raised (tightest: muted on raised at 4.75:1), so `ADJUSTMENTS` is empty.

There are no motion, shadow or grain tokens: texture and motion are effects,
and NoFX ships none.
"""

from types import MappingProxyType

SPEC_COLORS = MappingProxyType(
    {
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
)

ADJUSTMENTS = MappingProxyType(
    {
        # All /demo values pass AA on every dark surface; nothing adjusted.
        # Entries would be: name -> (value, "spec X.XX:1 on <surface>; shipped Y.YY:1")
    }
)

COLORS = MappingProxyType(
    {name: ADJUSTMENTS[name][0] if name in ADJUSTMENTS else v for name, v in SPEC_COLORS.items()}
)

SURFACES = ("bg", "panel", "raised")
TEXT = ("ink", "muted", "positive", "negative", "attention", "focus")
# WCAG 1.4.11: 3:1 for focus rings (state indicators). Rule tokens are
# decorative hairline separators, not state indicators (/demo precedent).
NON_TEXT = ("focus",)

TYPE = MappingProxyType(
    {
        "mono": (
            'ui-monospace, "JetBrains Mono", "SFMono-Regular", Menlo, Consolas, '
            '"Liberation Mono", monospace'
        ),
        "body_px": 12.5,  # /demo body
        "meta_px": 11.5,  # /demo disclosure line
        "headline_px": 17,  # /demo metric value
        "line_height": 1.45,
    }
)

SPACE = MappingProxyType({"1": "4px", "2": "8px", "3": "12px", "4": "16px", "6": "24px"})
RADIUS = "0"  # NoFX: no radius flourishes (the /demo terminal has none)
RULE_WIDTH = "1px"


def _channel(c: int) -> float:
    x = c / 255
    return x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {hex_color!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hex_color: str) -> float:
    r, g, b = (_channel(c) for c in rgb(hex_color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def contrast_report() -> list[dict]:
    """Every shipped text/surface pair with its measured ratio (report rows)."""
    rows = []
    for surface in SURFACES:
        for fg in TEXT:
            ratio = contrast(COLORS[fg], COLORS[surface])
            rows.append(
                {
                    "fg": fg,
                    "surface": surface,
                    "ratio": round(ratio, 2),
                    "aa_text": ratio >= 4.5,
                }
            )
    return rows
