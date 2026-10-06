"""Warm paper design tokens (DASHBOARD-SPEC "Reference and visual direction").

The spec lists proposed values and asks for contrast validation in
implementation. `SPEC_COLORS` keeps the proposed values verbatim; `COLORS` is
what ships. A text token differs from the spec only where the spec value fails
WCAG AA (4.5:1) on a paper surface under the worst-case grain composite; each
change is the smallest lightness reduction (same hue and saturation) that
clears 4.6:1, and is listed in `ADJUSTMENTS`.
"""

from types import MappingProxyType

SPEC_COLORS = MappingProxyType(
    {
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
)

ADJUSTMENTS = MappingProxyType(
    {
        "positive": ("#266F4B", "spec 4.45:1 on paper under 3% grain"),
        "attention": ("#895912", "spec 4.40:1 on plain paper (4.12:1 under grain)"),
        "focus": ("#326982", "spec 4.40:1 on paper under 3% grain"),
    }
)

COLORS = MappingProxyType(
    {name: ADJUSTMENTS[name][0] if name in ADJUSTMENTS else v for name, v in SPEC_COLORS.items()}
)

SURFACES = ("paper", "raised")
TEXT = ("ink", "muted", "positive", "negative", "attention", "focus")
NON_TEXT = ("rule-strong", "focus")  # WCAG 1.4.11: 3:1 for UI boundaries and focus rings

GRAIN = MappingProxyType(
    {
        "opacity": 0.03,  # spec: start at 2-4%
        "tile_px": 96,
        "seed": 3105,
        "levels": (0, 255),  # full-range monochrome: contrast math uses black/white extremes
    }
)

TYPE = MappingProxyType(
    {
        "sans": '"Inter", "Source Sans 3", "Helvetica Neue", Arial, sans-serif',
        "mono": '"IBM Plex Mono", "JetBrains Mono", ui-monospace, Menlo, monospace',
        "body_px": 15,  # spec 14-16
        "meta_px": 12.5,  # spec 12-13
        "headline_px": 26,  # spec 22-28
        "line_height": 1.45,
    }
)

SPACE = MappingProxyType({"1": "4px", "2": "8px", "3": "12px", "4": "16px", "6": "24px"})
RADIUS = "3px"  # compact corners
RULE_WIDTH = "1px"
SHADOW = "0 1px 0 rgba(41, 39, 34, 0.06)"  # restrained

MOTION_MS = MappingProxyType(
    {
        "kpi-highlight": 600,
        "depth": 200,  # spec 150-250
        "signal-select": 150,  # spec ~150
        "edge-pulse": 400,
        "drawer": 200,  # spec 180-240
    }
)


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


def composite(base: str, overlay: str, alpha: float) -> str:
    """`overlay` at `alpha` over opaque `base` (source-over)."""
    mixed = (
        round(b * (1 - alpha) + o * alpha) for b, o in zip(rgb(base), rgb(overlay), strict=True)
    )
    return "#{:02X}{:02X}{:02X}".format(*mixed)


def grain_extremes(surface: str, opacity: float | None = None) -> tuple[str, str]:
    """Darkest and lightest backgrounds a grain pixel can produce under text."""
    a = GRAIN["opacity"] if opacity is None else opacity
    lo, hi = GRAIN["levels"]
    return composite(surface, f"#{lo:02X}{lo:02X}{lo:02X}", a), composite(
        surface, f"#{hi:02X}{hi:02X}{hi:02X}", a
    )


def worst_contrast(fg: str, surface: str, grain: bool) -> float:
    if not grain:
        return contrast(fg, surface)
    return min(contrast(fg, bg) for bg in grain_extremes(surface))


def contrast_report() -> list[dict]:
    """Every shipped text/surface pair, grain off and on (accessibility report rows)."""
    rows = []
    for surface in SURFACES:
        for fg in TEXT:
            for grain in (False, True):
                ratio = worst_contrast(COLORS[fg], COLORS[surface], grain)
                rows.append(
                    {
                        "fg": fg,
                        "surface": surface,
                        "grain": grain,
                        "ratio": round(ratio, 2),
                        "aa_text": ratio >= 4.5,
                    }
                )
    return rows
