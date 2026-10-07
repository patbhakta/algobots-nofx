"""ALG-3264 decision quality: append-only log, settlement arithmetic, no-edge labels."""

import json
from datetime import datetime

import pytest

from algobots.contracts.decision import DecisionResponse, Usage
from algobots.demo import decisions as D
from algobots.demo import ledger as L
from algobots.demo.page import render


def _row(i: int, p: float, outcome: int, choice: str | None = "up") -> L.Row:
    return L.Row(
        event=f"KXBTC15M-26OCT06{i:04d}",
        strike=85000.0,
        outcome=outcome,
        ts=1791244800.0 + i * 900,
        p=p,
        conf=0.1,
        jev_p=0.6 if choice else None,
        jev_conf=0.4 if choice else None,
        jev_choice=choice,
    )


def _rec(strategy: str, i: int, rating: str, p_up: float | None) -> dict:
    return {
        "decision_id": D.decision_id(strategy, f"E{i}"),
        "strategy": strategy,
        "instrument_id": f"E{i}",
        "decided_at": f"2026-10-06T00:{i % 60:02d}:00+00:00",
        "status": "VALID",
        "rating": rating,
        "p_up": p_up,
        "reason": f"r{i}",
    }


def test_reingest_is_idempotent_and_append_only(tmp_path):
    path = tmp_path / D.LOG_FILE
    lg = L.build([_row(0, 0.60, 1), _row(1, 0.51, 0)])
    assert D.ingest(path, D.records(lg)) == 6  # 3 strategies x 2 intervals
    first = path.read_text()
    assert D.ingest(path, D.records(lg)) == 0
    assert path.read_text() == first
    # a new interval appends only its own decisions; earlier lines are untouched
    lg2 = L.build([_row(0, 0.60, 1), _row(1, 0.51, 0), _row(2, 0.40, 0)])
    assert D.ingest(path, D.records(lg2)) == 3
    assert path.read_text().startswith(first)
    ids = [json.loads(x)["decision_id"] for x in path.read_text().splitlines()]
    assert len(ids) == len(set(ids)) == 9


def test_load_dedupes_first_write_wins_and_skips_garbage(tmp_path):
    path = tmp_path / D.LOG_FILE
    a, b = _rec("laya", 1, "up", 0.6), _rec("laya", 1, "down", 0.4)
    path.write_text(json.dumps(a) + "\nnot json\n" + json.dumps(b) + "\n")
    assert D.load(path) == [a]


def test_record_holds_no_outcome_and_matches_decision_contract():
    lg = L.build([_row(0, 0.60, 1, choice=None), _row(1, 0.51, 0)])
    recs = {r["decision_id"]: r for r in D.records(lg)}
    assert all("outcome" not in r for r in recs.values())
    laya = recs["laya:KXBTC15M-26OCT060000"]
    assert (laya["status"], laya["rating"], laya["side"], laya["p_up"]) == (
        "VALID",
        "up",
        "YES",
        0.6,
    )
    assert recs["laya:KXBTC15M-26OCT060001"]["status"] == "ABSTAIN"  # within ±2pp
    assert recs["jev:KXBTC15M-26OCT060000"]["status"] == "UNAVAILABLE"
    assert recs["coin:KXBTC15M-26OCT060000"]["confidence"] is None  # never invented
    for r in recs.values():  # the log lifts into DecisionResponse@1.0 unchanged
        t = datetime.fromisoformat(r["decided_at"])
        DecisionResponse(
            schema_version=r["schema_version"],
            request_id=r["request_id"],
            status=r["status"],
            answers=r["answers"],
            confidence=r["confidence"],
            provider=r["provider"],
            model_revision=r["model_revision"] or "unpinned",
            usage=Usage(input_tokens=0, output_tokens=0),
            started_at=t,
            completed_at=t,
            receipt_ref=r["receipt_ref"] or "none",
        )


def test_settlement_arithmetic():
    recs = [
        _rec("laya", 0, "up", 0.70),  # hit:  brier 0.09, edge +0.50
        _rec("laya", 1, "up", 0.60),  # miss: brier 0.36, edge -0.50
        _rec("laya", 2, "down", 0.20),  # hit:  brier 0.04, edge +0.50
        _rec("laya", 3, "up", 0.55),  # unsettled: interval still open
        {**_rec("laya", 4, None, None), "status": "ABSTAIN"},  # never scored
    ]
    st = D.settle(recs, {"E0": 1, "E1": 0, "E2": 0, "E4": 1})
    assert [s.hit for s in st] == [True, False, True]
    assert [round(s.brier, 4) for s in st] == [0.09, 0.36, 0.04]
    sc = D.score(st, "laya")
    assert (sc.n, sc.hits) == (3, 2)
    assert sc.hit_rate == pytest.approx(2 / 3)
    assert sc.brier == pytest.approx((0.09 + 0.36 + 0.04) / 3)
    assert sc.mean_edge == pytest.approx(2 / 3 - 0.5)
    # a missing probability (coin) scores as 0.50 -> Brier 0.25
    assert D.settle([_rec("coin", 0, "down", None)], {"E0": 1})[0].brier == 0.25


def _scored(hits: int, n: int) -> D.Score:
    recs = [_rec("jev", i, "up", 0.6) for i in range(n)]
    return D.score(D.settle(recs, {f"E{i}": int(i < hits) for i in range(n)}), "jev")


@pytest.mark.parametrize(
    ("hits", "n", "label"),
    [
        (0, 0, "no settled decisions"),
        (20, 20, "n=20 < 30"),  # 100% hit rate still proves nothing at n=20
        (20, 40, "edge ≤ 0"),  # exactly 50%
        (12, 40, "edge ≤ 0"),
        (24, 40, "within 2σ of zero"),  # +10¢, 2σ ≈ 15.5¢
    ],
)
def test_no_edge_proven_labels(hits, n, label):
    sc = _scored(hits, n)
    assert sc.verdict.startswith("no edge proven") and label in sc.verdict
    assert not sc.proven


def test_edge_beyond_two_sigma_is_labelled_but_not_overclaimed():
    sc = _scored(32, 40)  # 80%: +30¢, 2σ ≈ 12.6¢
    assert sc.proven and "no edge proven" not in sc.verdict
    assert "not yet out-of-sample" in sc.verdict


def test_reflection_lists_recent_losses_with_bounded_lessons(tmp_path):
    lg = L.build([_row(i, 0.70, 0) for i in range(3)])
    (tmp_path / D.LESSONS_FILE).write_text(
        json.dumps({"decision_id": "laya:KXBTC15M-26OCT060002", "lesson": "x" * 999}) + "\n"
    )
    q = D.sync(tmp_path, lg)
    lost = D.losses(q.settled, "laya")
    assert [x.rec["instrument_id"][-4:] for x in lost] == ["0002", "0001", "0000"]
    assert all(x.rec["reason"] for x in lost)
    assert len(q.lessons["laya:KXBTC15M-26OCT060002"]) == D.LESSON_MAX
    html = render(lg, start="2026-10-06", now=lg.last_ts, quality=q)
    assert "Decision quality" in html and "no edge proven" in html.lower()
    assert "never fed back into live decisions" in html


def test_debate_pairs_opposite_calls_and_settlement_names_the_winner():
    recs = [
        _rec("laya", 1, "up", 0.6),
        _rec("jev", 1, "down", 0.4),  # clash, settles up -> laya (bull) wins
        _rec("laya", 2, "down", 0.4),
        _rec("jev", 2, "up", 0.6),  # clash, settles up -> jev (bull) wins
        _rec("laya", 3, "up", 0.6),
        _rec("jev", 3, "up", 0.6),  # agreement, hit
        _rec("laya", 4, "up", 0.6),
        _rec("jev", 4, "down", 0.4),  # clash, not settled yet
        _rec("laya", 5, "up", 0.6),  # jev silent -> no debate
        _rec("coin", 1, "down", 0.5),  # the control never debates
    ]
    d = D.debate(recs, {"E1": 1, "E2": 1, "E3": 1, "E5": 0})
    assert [x.event for x in d.clashes] == ["E4", "E2", "E1"]  # newest first
    assert d.clashes[2].bull["strategy"] == "laya" and d.clashes[2].bear["strategy"] == "jev"
    assert [x.winner for x in d.clashes] == [None, "jev", "laya"]
    assert d.wins == {"laya": 1, "jev": 1}
    assert (d.settled, d.agreed, d.agreed_hits) == (2, 1, 1)


def test_debate_needs_both_debaters_in_scope_and_renders():
    rows = [_row(0, 0.40, 1, "up"), _row(1, 0.60, 1, "up")]
    lg = L.build(rows)
    q = D.quality(D.records(lg), lg)
    assert q.debate is not None and len(q.debate.clashes) == 1
    assert q.debate.wins == {"laya": 0, "jev": 1}
    assert D.quality(D.records(lg), lg, accounts=["laya", "coin"]).debate is None
    html = render(lg, start="2026-10-06", quality=q)
    assert "Analyst debate · bull vs bear" in html
    assert "no debate outcome changes an order" in html
