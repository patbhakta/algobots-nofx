"""ALG-3248 demo ledger: sizing, fees, risk rails, kill switch, page render."""

import json
from decimal import Decimal

from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo.page import render


def _row(i: int, p: float, outcome: int, choice: str = "up", conf: float = 0.5) -> L.Row:
    return L.Row(
        event=f"KXBTC15M-26OCT06{i:04d}",
        strike=85000.0,
        outcome=outcome,
        ts=1791244800.0 + i * 900,  # 2026-10-06T00:00Z + i intervals
        p=p,
        conf=0.1,
        jev_p=0.6,
        jev_conf=conf,
        jev_choice=choice,
    )


def test_fee_matches_kalshi_taker_formula():
    # $10 at 50c = 20 contracts; 0.07 * 20 * 0.25 = 0.35
    assert L.fee_for(Decimal("10")) == Decimal("0.35")
    assert L.fee_for(Decimal("5")) == Decimal("0.18")  # 0.175 rounds up


def test_laya_abstains_without_edge_and_sizes_within_5_to_15():
    lg = L.build([_row(0, 0.51, 1), _row(1, 0.60, 1), _row(2, 0.53, 0)])
    d0, d1, d2 = lg.books["laya"].decisions
    assert d0.status == "ABSTAIN"
    assert d1.status == "FILLED" and d1.side == "YES" and d1.won
    assert d1.requested == Decimal("25.00") and d1.stake == Decimal("15") and d1.clamped
    assert d1.pnl == Decimal("15") - L.fee_for(Decimal("15"))
    assert d2.side == "YES" and not d2.won and Decimal("5") <= d2.stake <= Decimal("15")
    assert all(Decimal("5") <= d.stake <= Decimal("15") for b in lg.books.values() for d in b.fills)


def test_daily_loss_envelope_blocks_entries_after_cap():
    rows = [_row(i, 0.70, 0) for i in range(6)]  # Laya bets YES $15, loses every time
    book = L.build(rows).books["laya"]
    statuses = [d.status for d in book.decisions]
    assert statuses[:3] == ["FILLED"] * 3  # 3 x ~-15.53 = -46.58 >= 40 cap
    assert statuses[3:] == ["BLOCKED"] * 3
    assert "daily-loss envelope" in book.decisions[3].reason


def test_sleeve_never_goes_negative():
    # alternate days so the daily-loss cap never trips; every bet loses
    rows = [
        L.Row(f"E{i}", 1.0, 0, 1791244800.0 + i * 86400, 0.70, 0.1, None, None, None)
        for i in range(20)
    ]
    book = L.build(rows).books["laya"]
    assert book.equity >= 0
    assert book.decisions[-1].status == "BLOCKED"
    assert "below minimum stake" in book.decisions[-1].reason


def test_kill_switch_blocks_entries_from_engagement(tmp_path):
    state = killswitch.set_engaged(str(tmp_path), True, actor="test", now=_row(2, 0, 0).ts)
    lg = L.build([_row(i, 0.60, 1) for i in range(4)], state)
    assert [d.status for d in lg.books["laya"].decisions] == [
        "FILLED",
        "FILLED",
        "BLOCKED",
        "BLOCKED",
    ]
    released = killswitch.set_engaged(str(tmp_path), False, actor="test")
    assert not released["engaged"] and len(released["history"]) == 2


def test_load_rows_skips_bad_lines_and_filters_start(tmp_path):
    f = tmp_path / "obs.jsonl"
    good = {"event": "E1", "strike": 1, "outcome": 1, "p": 0.6, "ts": 200.0}
    f.write_text("not json\n" + json.dumps(good) + "\n" + json.dumps({**good, "ts": 50.0}) + "\n")
    assert [r.ts for r in L.load_rows(f, since_ts=100)] == [200.0]


def test_page_renders_paper_only_with_all_panels():
    lg = L.build([_row(i, 0.45 + 0.03 * (i % 4), i % 2) for i in range(12)])
    html = render(lg, start="2026-10-06", now=lg.last_ts + 60)
    for needle in (
        "PAPER TRADING",
        "Strategy performance",
        "Risk state",
        "Kill switch",
        "Recent decisions and reasons",
        "Accounts",
        "Laya System One",
        "<svg",
    ):
        assert needle in html
    assert "LIVE" not in html.replace("Live", "")  # no live-environment badge anywhere


def test_refill_tops_sleeve_up_as_capital_not_pnl():
    rows = [
        L.Row(f"E{i}", 1.0, 0, 1791244800.0 + i * 86400, 0.70, 0.1, None, None, None)
        for i in range(20)
    ]
    plain = L.build(rows).books["laya"]
    refill_at = rows[15].ts
    book = L.build(rows, refills=[refill_at]).books["laya"]
    assert plain.exhausted and len(book.refills) == 1
    ts, added = book.refills[0]
    assert ts == refill_at and added == L.SLEEVE - plain.curve[14][1]
    assert book.allocated == L.SLEEVE + added
    assert book.decisions[15].status == "FILLED"  # trades again after the refill
    assert book.equity == book.allocated + book.pnl  # P&L stays cumulative
    assert book.pnl < plain.pnl and book.max_drawdown <= plain.max_drawdown


def test_page_mobile_and_labelling_fixes():
    rows = [
        L.Row(f"E{i}", 1.0, 0, 1791244800.0 + i * 86400, 0.70, 0.1, "up", 0.5, "up")
        for i in range(20)
    ]
    lg = L.build(rows)
    html = render(lg, start="2026-10-03", now=lg.last_ts + 60)
    # disclosure is visible at every width (not inside a .wide span)
    assert "<span>simulated fills at assumed 50¢ mid" in html
    assert "DEMO DATA" not in html and "PAPER · SIMULATED FILLS" in html
    assert 'class="data stack"' in html and 'data-label="Reason"' in html
    assert 'class="chart-d"' in html and 'class="chart-m"' in html
    assert "sleeve exhausted — entries blocked" in html  # daily-loss State honours the sleeve
    assert "Stopped by risk rails" in html
    assert 'name="actor"' in html


def test_spread_keeps_labels_apart_and_in_bounds():
    from algobots.demo.page import _spread

    out = _spread({"a": 210.0, "b": 211.0, "c": 212.0, "d": 100.0}, 15, 12, 240)
    ys = sorted(out.values())
    assert all(b - a >= 15 for a, b in zip(ys, ys[1:], strict=False))
    assert ys[0] >= 12 and ys[-1] <= 240


def test_accounts_state_agrees_with_risk_and_return_ignores_refills():
    rows = [_row(i, 0.70, 0) for i in range(6)]  # Laya trips its daily cap after 3 losses
    lg = L.build(rows, refills=[rows[1].ts])
    html = render(lg, start="2026-10-06", now=lg.last_ts + 60)
    assert html.count("daily cap hit · resumes 00:00Z") >= 2  # risk table and accounts table
    laya = lg.books["laya"]
    pnl = sum((b.pnl for b in lg.books.values()), Decimal(0))
    assert laya.refills  # the refill landed after the first loss
    ret = f"{pnl / (L.SLEEVE * 3) * 100:.2f}"
    assert ret.lstrip("-") in html and "refills excluded" in html
