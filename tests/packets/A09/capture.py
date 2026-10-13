"""Capture A09 screenshots and the layout audit headless (`make screenshots-A09`).

Writes PNGs to artifacts/A09/screenshots/ and artifacts/A09/layout-audit.json:
every screen at the four DASHBOARD-SPEC sizes (good fixture) and every
non-good fixture state at 1440x900 (overview also at 390x844).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from headless import ROOT, SIZES, audit, chrome, screenshot  # noqa: E402

from algobots.dashboard.design.storyboard import SCREENS  # noqa: E402
from algobots.dashboard.fixtures import STATES  # noqa: E402

OUT = ROOT / "artifacts" / "A09" / "screenshots"


def plan() -> list[tuple[str, str, dict]]:
    shots = [(f"{s}-good.html", size, {}) for s in SCREENS for size in SIZES]
    shots += [(f"{s}-{st}.html", "1440x900", {}) for s in SCREENS for st in STATES if st != "good"]
    shots += [(f"overview-{st}.html", "390x844", {}) for st in STATES if st != "good"]
    return shots


def main() -> int:
    if chrome() is None:
        print("BLOCKED: no headless Chrome/Chromium available (set A09_CHROME)")
        return 2
    report = []
    for page, size, query in plan():
        suffix = "".join(f"-{k}-{v}" for k, v in query.items())
        out = OUT / f"{page.removesuffix('.html')}-{size}{suffix}.png"
        screenshot(page, SIZES[size], out, **query)
        result = audit(page, SIZES[size], **query)
        report.append(
            {
                "page": page,
                "size": size,
                "query": query,
                "png": out.relative_to(ROOT).as_posix(),
                "overflowing": result["overflowing"],
                "clipped": result["clipped"],
                "scroll_within_viewport": result["scrollWidth"] <= result["innerWidth"],
            }
        )
    (ROOT / "artifacts" / "A09" / "layout-audit.json").write_text(
        json.dumps({"browser": Path(chrome()).name, "pages": report}, indent=2) + "\n"
    )
    bad = [r for r in report if r["overflowing"] or r["clipped"] or not r["scroll_within_viewport"]]
    print(f"{len(report)} screenshots; {len(bad)} with horizontal overflow")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
