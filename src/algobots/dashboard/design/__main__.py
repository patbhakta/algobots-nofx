"""Build A09 outputs deterministically: `python -m algobots.dashboard.design build <out_dir>`.

Writes the storyboard pages, `tokens.json`, `tokens.css`, `components.json`,
`accessibility-contrast.json` and one JSON file per fixture state under
`<out_dir>/fixtures/`. Re-running on an unchanged tree produces identical bytes.
"""

import argparse
import json
import sys
from pathlib import Path

from algobots.dashboard.design import components, grain, storyboard, tokens
from algobots.dashboard.design.css import stylesheet
from algobots.dashboard.fixtures import all_fixtures


def _dump(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build(out: Path) -> None:
    storyboard.build(out / "storyboard")
    fixtures = out / "fixtures"
    fixtures.mkdir(parents=True, exist_ok=True)
    for state, data in all_fixtures().items():
        _dump(fixtures / f"{state}.json", data)
    _dump(
        out / "tokens.json",
        {
            "spec_colors": dict(tokens.SPEC_COLORS),
            "colors": dict(tokens.COLORS),
            "adjustments": {
                k: {"value": v, "reason": r} for k, (v, r) in tokens.ADJUSTMENTS.items()
            },
            "grain": dict(tokens.GRAIN) | {"tile_sha256": grain.tile_sha256()},
            "type": dict(tokens.TYPE),
            "space": dict(tokens.SPACE),
            "radius": tokens.RADIUS,
            "rule_width": tokens.RULE_WIDTH,
            "motion_ms": dict(tokens.MOTION_MS),
        },
    )
    (out / "tokens.css").write_text(stylesheet(), encoding="utf-8")
    _dump(out / "components.json", [{"name": n, "purpose": p} for n, p in components.INVENTORY])
    _dump(out / "accessibility-contrast.json", tokens.contrast_report())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m algobots.dashboard.design")
    parser.add_argument("command", choices=["build"])
    parser.add_argument("out", type=Path)
    args = parser.parse_args(argv)
    build(args.out)
    print(f"A09 outputs written to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
