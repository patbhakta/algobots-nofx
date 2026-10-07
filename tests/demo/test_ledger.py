"""ALG-3248 demo ledger: sizing, fees, risk rails, kill switch, page render."""

import json
from decimal import Decimal

from algobots.demo import blotter as B
from algobots.demo import killswitch
from algobots.demo import ledger as L
from algobots.demo.page import VIEWS, render


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


def _every_view(lg: L.Ledger, **kw) -> str:
    """All tabs concatenated: every pane must stay reachable from /demo (ALG-3288)."""
    return "".join(render(lg, view=v, **kw) for v in VIEWS)


def test_overview_reads_cold_without_the_dense_panes():
    lg = L.build([_row(i, 0.45 + 0.03 * (i % 4), i % 2) for i in range(12)])
    html = render(lg, start="2026-10-06", now=lg.last_ts + 60)
    assert 'data-view="overview"' in html and "Needs your attention" in html
    assert "paper-trading Kalshi" in html and "No real money is at risk" in html
    assert html.count("data-card=") == 3 and html.count('class="spark"') == 3
    assert '<svg class="chart-d"' in html and "data-pts=" in html  # hover-able hero chart
    assert "Flat — no open positions" in html and "All orders →" in html
    for dense in ('aria-label="Orders"', 'aria-label="Risk"', 'aria-label="Accounts"', "<table"):
        assert dense not in html, dense  # dense panes live behind tabs
    for k, label in VIEWS.items():
        assert f'data-view="{k}">{label}' in html.replace("&amp;", "&"), k
    assert 'href="/demo?account=laya"' in html  # card drills in
    halted = L.build([_row(i, 0.70, 0) for i in range(6)])  # Laya trips its daily cap
    assert "Laya System One stopped trading" in render(halted, start="x", now=halted.last_ts + 60)


def test_page_renders_paper_only_with_all_panels():
    lg = L.build([_row(i, 0.45 + 0.03 * (i % 4), i % 2) for i in range(12)])
    html = _every_view(lg, start="2026-10-06", now=lg.last_ts + 60)
    for needle in (
        "PAPER TRADING",
        "Strategy performance",
        "Accounts",
        "Positions",
        "Orders",
        "Risk",
        "Kill switch",
        "No open positions",  # everything settled -> explicit empty state
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
    html = _every_view(lg, start="2026-10-03", now=lg.last_ts + 60)
    # disclosure is visible at every width (not inside a .wide span)
    assert "<span>simulated fills at assumed 50¢ mid" in html
    assert "DEMO DATA" not in html and "PAPER · SIMULATED FILLS" in html
    assert 'class="data stack"' in html and 'data-label="Reason"' in html
    assert 'class="chart-d"' in html and 'class="chart-m"' in html
    assert html.count("HALT SLEEVE EXHAUSTED") >= 2  # accounts + risk honour the sleeve
    assert 'name="actor"' in html


def test_spread_keeps_labels_apart_and_in_bounds():
    from algobots.demo.page import _spread

    out = _spread({"a": 210.0, "b": 211.0, "c": 212.0, "d": 100.0}, 15, 12, 240)
    ys = sorted(out.values())
    assert all(b - a >= 15 for a, b in zip(ys, ys[1:], strict=False))
    assert ys[0] >= 12 and ys[-1] <= 240


def _states(html: str, pane: str, account: str) -> dict[str, str]:
    """Account name -> state label for each per-account row in a pane."""
    import re

    sec = html.split(f'aria-label="{pane}"')[1].split("</section>")[0]
    out = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", sec):
        name = re.search(r"(Laya System One|Jev zero-shot|Coin-flip control)", tr)
        state = re.search(
            r'data-label="State"><span class="status[^"]*" [^>]*aria-label="([^"]+)"', tr
        )
        if name and state:
            out[name.group(1)] = state.group(1)
    assert out and (pane == "Accounts" or account == "all" or len(out) == 1)
    return out


def test_accounts_state_agrees_with_risk_and_return_ignores_refills():
    rows = [_row(i, 0.70, 0) for i in range(6)]  # Laya trips its daily cap after 3 losses
    lg = L.build(rows, refills=[rows[1].ts])
    html = _every_view(lg, start="2026-10-06", now=lg.last_ts + 60)
    # regression: Accounts and Risk states agree, in the aggregate and in each account context
    for account in ("all", *L.STRATEGIES):
        page = _every_view(lg, start="2026-10-06", now=lg.last_ts + 60, account=account)
        risk = _states(page, "Risk", account)  # filtered to the context
        assert {k: v for k, v in _states(page, "Accounts", account).items() if k in risk} == risk
    assert "HALT DAILY CAP HIT · RESUMES 00:00Z" in _states(html, "Risk", "all")["Laya System One"]
    laya = lg.books["laya"]
    pnl = sum((b.pnl for b in lg.books.values()), Decimal(0))
    assert laya.refills  # the refill landed after the first loss
    ret = f"{pnl / (L.SLEEVE * 3) * 100:.2f}"
    assert ret.lstrip("-") in html and "refills excluded" in html


def test_account_context_filters_every_pane_and_round_trips_in_url():
    lg = L.build([_row(i, 0.45 + 0.03 * (i % 4), i % 2) for i in range(12)])
    now = lg.last_ts + 60
    html = _every_view(lg, start="2026-10-06", now=now, account="jev", status="filled")
    assert 'data-account="jev"' in html and 'class="acct sel" data-account="jev"' in html
    # overview: positions + activity; Positions, Orders, Risk, Ticket blotter, 3 quality panes
    assert html.count("ctx: Jev zero-shot") == 9
    orders = html.split('aria-label="Orders"')[1].split("</section>")[0]
    assert "Jev zero-shot" in orders and "Laya System One" not in orders
    # filters keep the context and the tab
    assert 'href="/demo?account=jev&amp;view=orders&amp;status=blocked"' in orders
    for k in VIEWS:  # every tab keeps the account context
        assert f'href="/demo?account=jev&amp;view={k}"' in html or k == "overview", k
    assert 'name="account" value="jev"' in html  # kill switch returns to the same context
    workers = {
        "laya": {
            "account": "laya",
            "state": "ready",
            "pid": 41,
            "rss_mb": 88.0,
            "last_heartbeat": now - 5,
        },
        "jev": {"account": "jev", "state": "exited", "exit_code": 1},
    }
    w = render(lg, start="x", now=now, workers=workers, view="accounts")
    assert 'READY</span> <span class="meta">pid 41 · 88MB · hb 5s ago' in w
    assert 'data-status="BLOCKED"' in w and "EXITED (1)" in w  # exited reads as an alert
    assert "1/3 ready" in w
    bogus = render(lg, start="x", now=now, account="bogus")  # unknown -> aggregate
    assert bogus.count('class="acct sel" data-account="all"') == 1


def test_blotter_orders_newest_first_and_open_positions():
    rows = [_row(i, 0.60, i % 2) for i in range(4)]
    lg = L.build(rows)
    out = B.orders(lg, "laya")
    assert [o["ts"] for o in out] == sorted((o["ts"] for o in out), reverse=True)
    assert {o["status"] for o in B.orders(lg, B.ALL, "filled")} == {"filled"}
    assert B.positions(lg, rows[-1].ts + 1) == []  # all settled
    live = B.positions(lg, rows[-1].ts - 60, "laya")
    assert len(live) == 1 and live[0]["qty"] == int(Decimal(out[0]["notional"]) / L.FILL_PRICE)
    assert live[0]["expires_in_s"] == 60


def test_positions_and_orders_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    feed = tmp_path / "observations.jsonl"
    feed.write_text(
        "\n".join(
            json.dumps(
                {
                    "event": f"E{i}",
                    "strike": 1,
                    "outcome": i % 2,
                    "ts": 1791244800 + i * 900,
                    "p": 0.6,
                    "conf": 0.1,
                    "jev_choice": "up",
                    "jev_conf": 0.5,
                    "jev_p": 0.6,
                }
            )
            for i in range(5)
        )
    )
    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(feed))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_DEMO_START", "2026-10-06")
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        pos = client.get("/demo/api/positions?account=laya").json()
        assert pos["account"] == "laya" and pos["positions"] == []
        body = client.get("/demo/api/orders?account=jev&status=filled&limit=3").json()
        assert body["account"] == "jev" and body["status"] == "filled" and len(body["orders"]) == 3
        assert all(o["account"] == "jev" and o["status"] == "filled" for o in body["orders"])
        assert len(client.get("/demo/api/orders").json()["orders"]) == 15
        page = client.get("/demo?account=coin")
        assert page.status_code == 200 and 'class="acct sel" data-account="coin"' in page.text
        r = client.post(
            "/demo/kill-switch", data={"engaged": "on", "account": "coin"}, follow_redirects=False
        )
        assert r.status_code == 303 and r.headers["location"] == "/demo?account=coin&view=risk"
    finally:
        get_settings.cache_clear()
