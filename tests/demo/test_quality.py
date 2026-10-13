"""ALG-3267 decision quality + reflection pane: harness parity, settlement gate, account filter."""

import json

import pytest
from tests.demo.test_scope import _scope

from algobots.api.config import get_settings
from algobots.demo import ledger as L
from algobots.demo import quality as Q
from algobots.demo.page import render
from algobots.demo.scope import current_scope
from algobots.evals.harness import summarize

OUTCOMES = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1]
NOW = 1791244800.0 + 20 * 900
PS = [0.60, 0.45, 0.53, 0.70, 0.40, 0.51, 0.58, 0.62, 0.35, 0.56, 0.49, 0.66]


def _feed() -> list[L.Row]:
    return [
        L.Row(
            event=f"KXBTC15M-26OCT06{i:04d}",
            strike=85000.0,
            outcome=o,
            ts=1791244800.0 + i * 900,
            p=p,
            conf=0.1,
            jev_p=1 - p,
            jev_conf=0.4,
            jev_choice="down" if p > 0.5 else "up",
        )
        for i, (o, p) in enumerate(zip(OUTCOMES, PS, strict=True))
    ]


def _pending_row() -> L.Row:
    return L.Row(
        "KXBTC15M-26OCT069999", 85000.0, -1, 1791244800.0 + 99 * 900, 0.64, 0.1, 0.3, 0.4, "down"
    )


def test_pane_numbers_equal_harness_output_for_fixture_feed():
    lg = L.build(_feed())
    q = Q.quality(lg)
    html = render(lg, start="2026-10-06", now=NOW, harness=q, view="quality")
    for key, cs in Q.calls(lg).items():
        expected = summarize([Q._record(c) for c in cs])
        s = q["strategies"][key]
        assert s["brier"] == expected.brier
        assert s["hit_rate"] == expected.overall.hit_rate
        assert s["sample_size"] == expected.overall.count
        assert s["edge_demonstrated"] == bool(expected.edge_demonstrated)
        assert s["harness"] == expected.to_dict()
        assert f'data-q="brier">{expected.brier:.4f}<' in html
    # Laya abstains on |p - 0.5| < 0.02 (rows 5, 10): 10 calls, 8 hits.
    laya = q["strategies"]["laya"]
    assert (laya["settled"], laya["pending"], laya["hit_rate"]) == (10, 0, 0.8)
    assert q["strategies"]["coin"]["brier"] == pytest.approx(0.5)  # coin = 0.5/0.5 everywhere
    assert q["strategies"]["coin"]["coin_brier"] == pytest.approx(0.5)
    # small n: the harness does not certify, so the pane must not either
    assert all(s["verdict"] == "NO VALIDATED EDGE" for s in q["strategies"].values())
    assert "no validated edge" in html and "edge demonstrated" not in html
    assert all(s["random_control"]["seeds"] == Q.RANDOM_SEEDS for s in q["strategies"].values())
    cal = laya["calibration"]
    assert sum(b["count"] for b in cal) == laya["settled"]


def test_reflection_exists_only_for_settled_decisions():
    lg = L.build(_feed())
    q = Q.quality(lg, [_pending_row()])
    laya = q["strategies"]["laya"]
    assert laya["pending"] == 1 and laya["settled"] == 10
    by = Q.calls(lg, [_pending_row()])
    pending = [c for c in by["laya"] if c.outcome is None]
    assert len(pending) == 1 and Q.reflection(pending[0]) is None
    settled_ids = {Q.decision_id("laya", c.event) for c in by["laya"] if c.outcome is not None}
    for s in q["strategies"].values():
        for r in s["reflections"]:
            assert r["decision_id"] != Q.decision_id(s["strategy"], _pending_row().event)
            assert r["namespace"] == f"investment/pat/accounts/{s['strategy']}"
    assert {r["decision_id"] for r in laya["reflections"]} <= settled_ids
    # reflections link to the decision row they reflect on, on the Orders tab
    html = render(lg, start="2026-10-06", now=NOW, harness=q, view="quality")
    orders = render(lg, start="2026-10-06", now=NOW, harness=q, view="orders")
    for r in laya["reflections"]:
        link = f'<a href="/demo?view=orders#o-{r["decision_id"]}"'
        assert f'data-decision="{r["decision_id"]}">{link}' in html
        assert f'id="o-{r["decision_id"]}"' in orders


def test_account_context_filters_the_pane():
    lg = L.build(_feed())
    q = Q.quality(lg, account="jev")
    assert list(q["strategies"]) == ["jev"] and q["account"] == "jev"
    html = render(lg, start="2026-10-06", now=NOW, account="jev", harness=q, view="quality")
    pane = html.split('aria-label="Harness verdict · calibration · reflections"')[1].split(
        "</section>"
    )[0]
    assert "Jev zero-shot" in pane and "Laya System One" not in pane
    assert set(Q.quality(lg)["strategies"]) == {"laya", "jev", "coin"}
    with pytest.raises(KeyError):
        Q.quality(lg, account="nobody")


@pytest.fixture
def grant(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.main import app

    feed = tmp_path / "observations.jsonl"
    lines = [json.dumps(r.__dict__) for r in _feed()]
    lines.append(json.dumps(_pending_row().__dict__ | {"outcome": None}))
    feed.write_text("\n".join(lines) + "\n")
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_DEMO_START", "2026-10-01")
    get_settings.cache_clear()

    def make(*accounts: str) -> TestClient:
        app.dependency_overrides[current_scope] = lambda: _scope(*accounts)
        return TestClient(app)

    try:
        yield make
    finally:
        app.dependency_overrides.pop(current_scope, None)
        get_settings.cache_clear()


def test_quality_endpoint_follows_account_context_and_grants(grant):
    c = grant("laya", "jev", "coin")
    full = c.get("/demo/api/quality").json()
    assert full["account"] == "all" and set(full["strategies"]) == {"laya", "jev", "coin"}
    assert full["strategies"]["laya"]["pending"] == 1
    one = c.get("/demo/api/quality?account=coin").json()
    assert list(one["strategies"]) == ["coin"]
    assert one["strategies"]["coin"] == full["strategies"]["coin"]
    assert c.get("/demo/api/quality?account=nobody").status_code == 404
    assert (
        'aria-label="Harness verdict · calibration · reflections"'
        in c.get("/demo?account=laya&view=quality").text
    )
    partial = grant("laya").get("/demo/api/quality").json()
    assert list(partial["strategies"]) == ["laya"]  # ungranted accounts never leave the server
