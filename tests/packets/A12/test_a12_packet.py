"""A12-1 (ALG-3257) packet checks: the demo card, the gate doc, the make target.

The full walkthrough itself is `make demo-g1` (needs the `workers` extra);
these tests pin its always-on surfaces so a regression fails `pytest -q`.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture()
def page(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    now = int(time.time()) // 900 * 900
    feed = tmp_path / "observations.jsonl"
    feed.write_text(
        "\n".join(
            json.dumps(
                {
                    "event": f"E{i}",
                    "strike": 1,
                    "outcome": i % 2,
                    "ts": now - (12 - i) * 900,
                    "p": 0.6,
                    "conf": 0.1,
                    "jev_choice": "up",
                    "jev_conf": 0.5,
                    "jev_p": 0.6,
                }
            )
            for i in range(12)
        )
        + "\n"
    )
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_DEMO_START", time.strftime("%Y-%m-%d", time.gmtime(now - 86400)))
    get_settings.cache_clear()
    with TestClient(app) as client:
        yield client
    get_settings.cache_clear()


def _card(html: str) -> str:
    start = html.index('<details class="democard">')
    return html[start : html.index("</details>", start) + 9]


def test_terminal_carries_collapsible_five_step_card_at_the_top(page):
    html = page.get("/demo").text
    card = _card(html)
    # collapsible, pinned at the top of the terminal (inside .chrome, above main)
    assert card.startswith('<details class="democard"><summary>HOW TO DEMO G1')
    assert html.index('<details class="democard">') < html.index('<main id="main"')
    steps = card.count("<li>")
    assert steps == 5, steps
    for fragment in (
        "make demo-g1",
        "kill_switch",
        "reconciling",
        "artifacts/A12/",
        "docs/gates/G1/decision.md",
    ):
        assert fragment in card, fragment


def test_gate_decision_lists_all_four_call_categories_and_no_edge():
    doc = (ROOT / "docs" / "gates" / "G1" / "decision.md").read_text()
    for section in ("## Proven", "## Simulated", "## Blocked", "## Failed"):
        assert section in doc, section
    assert "no edge" in doc.lower()
    assert "C1" in doc and "C5" in doc


def test_makefile_exposes_demo_g1_running_the_a12_driver():
    makefile = (ROOT / "Makefile").read_text()
    assert "demo-g1:" in makefile
    assert "tests/packets/A12/demo.py" in makefile
    assert (ROOT / "tests" / "packets" / "A12" / "demo.py").exists()
    assert (ROOT / "tests" / "packets" / "A12" / "shots.mjs").exists()
