"""Order ticket (ALG-3265, ALG-3262): five paths, one risk gate on every leg, privileged exits."""

import json
from decimal import Decimal

import pytest

from algobots.demo import blotter as B
from algobots.demo import gate as G
from algobots.demo import ledger as L
from algobots.demo import tickets as T
from algobots.demo.page import render
from algobots.risk import BreakerConfig, RateBreakers, RiskGate

DAY0 = 1791244800  # 2026-10-06 00:00Z
NOW = DAY0 + 20 * 3600


def _row(i: int, outcome: int) -> L.Row:
    return L.Row(f"E{i}", 1.0, outcome, DAY0 + i * 900, 0.70, 0.5, 0.7, 0.9, "up")


def _ledger(kill: dict | None = None) -> L.Ledger:
    return L.build([_row(i, 1) for i in range(3)], kill)


def _losing_laya() -> L.Ledger:
    """laya + jev lose every interval today → laya trips the daily-loss envelope."""
    lg = L.build([_row(i, 0) for i in range(6)])
    assert L.ENVELOPE.check_daily_loss(B.day_pnl(lg.books["laya"], B.today(NOW))).tripped
    return lg


class SpyGate(RiskGate):
    """Counts every leg the risk gate sees."""

    def __init__(self, **kw):
        super().__init__(limits=T.LIMITS, envelope=L.ENVELOPE, **kw)
        self.seen: list[str] = []

    def approve_order(self, **kw):
        self.seen.append(kw["deployment_id"])
        return super().approve_order(**kw)


def _ids():
    n = iter(range(1000))
    return lambda: f"p{next(n)}"


def test_broadcast_to_three_with_one_daily_loss_denial_is_part_sent():
    lg = _losing_laya()
    lg.books["jev"].decisions.clear()  # jev and coin are fresh: only laya is over the cap
    lg.books["coin"].decisions.clear()
    p = T.submit(
        lg, "broadcast", T.broadcast(["laya", "jev", "coin"], "YES", Decimal("10")), now=NOW
    )
    assert p.state == "part_sent"
    legs = {x.account: x for x in p.legs}
    assert len(legs) == 3 and {x.parent_id for x in p.legs} == {p.id}
    assert legs["laya"].status == "blocked" and "daily-loss" in legs["laya"].reason
    assert legs["jev"].status == legs["coin"].status == "filled"
    assert legs["jev"].price == "0.50" and legs["jev"].fee == str(L.fee_for(Decimal("10")))


def test_split_respects_max_clip():
    p = T.submit(
        _ledger(), "split", [T.Intent("coin", "NO", Decimal("23"))], now=NOW, max_clip=Decimal("7")
    )
    assert [Decimal(x.requested) for x in p.legs] == [7, 7, 7, 2]
    assert all(Decimal(x.notional) <= 7 for x in p.legs) and p.state == "sent"
    assert sum(Decimal(x.notional) for x in p.legs) == 23
    with pytest.raises(T.TicketError):
        T.submit(_ledger(), "split", [T.Intent("coin", "NO", Decimal("5"))], now=NOW)


def test_kill_switch_denies_every_entry_leg_and_allows_exits():
    lg = _ledger({"engaged": True, "since_ts": NOW - 60})
    for path, intents, clip in (
        ("single", [T.Intent("laya", "YES", Decimal("5"))], None),
        ("broadcast", T.broadcast(L.STRATEGIES, "YES", Decimal("5")), None),
        (
            "basket",
            [T.Intent("laya", "YES", Decimal("5")), T.Intent("jev", "NO", Decimal("5"))],
            None,
        ),
        ("split", [T.Intent("coin", "YES", Decimal("12"))], Decimal("5")),
    ):
        p = T.submit(lg, path, intents, now=NOW, max_clip=clip)
        assert p.state == "rejected"
        assert all(x.status == "blocked" and "kill switch" in x.reason for x in p.legs)
    exits = T.submit(
        lg, "broadcast", T.broadcast(L.STRATEGIES, "NO", Decimal("40"), "exit"), now=NOW
    )
    assert exits.state == "sent" and all(x.status == "filled" for x in exits.legs)
    assert all(x.notional == "40" and not x.clamped for x in exits.legs)  # exits are never clamped


def test_rate_breaker_never_blocks_an_exit():
    gate = RiskGate(
        limits=T.LIMITS,
        envelope=L.ENVELOPE,
        breakers=RateBreakers(BreakerConfig(per_deployment_orders_per_minute=2)),
    )
    p = T.submit(
        _ledger(),
        "split",
        [T.Intent("laya", "YES", Decimal("15"))],
        now=NOW,
        max_clip=Decimal("5"),
        gate=gate,
    )
    assert [x.status for x in p.legs] == ["filled", "filled", "blocked"]
    assert p.state == "part_sent" and "per_deployment_orders_per_minute" in p.legs[2].reason
    ex = T.submit(
        _ledger(), "single", [T.Intent("laya", "NO", Decimal("5"), "exit")], now=NOW, gate=gate
    )
    assert ex.legs[0].status == "filled"


def test_entry_is_clamped_to_max_order_value():
    p = T.submit(_ledger(), "single", [T.Intent("laya", "YES", Decimal("40"))], now=NOW)
    assert p.legs[0].notional == str(L.ENVELOPE.max_order_value) and p.legs[0].clamped


def _bracket(lg: L.Ledger, accounts=("laya",), **kw) -> T.Parent:
    return T.submit(
        lg,
        "bracket",
        T.broadcast(list(accounts), "YES", Decimal("10")),
        now=NOW,
        take_profit=Decimal("0.70"),
        stop=Decimal("0.30"),
        new_id=_ids(),
        **kw,
    )


def test_bracket_is_entry_plus_working_take_profit_and_stop():
    p = _bracket(_ledger())
    assert [(x.role, x.kind, x.status) for x in p.legs] == [
        ("entry", "entry", "filled"),
        ("take_profit", "exit", "working"),
        ("stop", "exit", "working"),
    ]
    assert [x.price for x in p.legs] == ["0.50", "0.70", "0.30"]
    assert p.state == "sent" and "OCO with leg 1" in p.legs[1].reason
    with pytest.raises(T.TicketError, match="straddle"):
        T.submit(
            _ledger(),
            "bracket",
            [T.Intent("laya", "YES", Decimal("5"))],
            now=NOW,
            take_profit=Decimal("0.40"),
            stop=Decimal("0.30"),
        )


def test_bracket_cancel_cascades_to_working_children(tmp_path):
    sd = str(tmp_path)
    p = _bracket(_ledger(), ("laya", "jev"), state_dir=sd)
    assert sum(x.status == "working" for x in p.legs) == 4
    c = T.cancel(sd, p.id, now=NOW + 60)
    assert c.cancelled_ts == NOW + 60
    # fills are final; every resting child is cancelled with the parent
    assert [x.status for x in c.legs if x.role == "entry"] == ["filled", "filled"]
    kids = [x for x in c.legs if x.role != "entry"]
    assert len(kids) == 4 and all(x.status == "cancelled" for x in kids)
    assert all(x.reason.startswith(T.CANCEL_CASCADE) for x in kids)
    assert T.load(sd)[0].legs == c.legs  # persisted
    with pytest.raises(T.TicketError, match="unknown ticket"):
        T.cancel(sd, "nope", now=NOW)


def test_blocked_bracket_entry_places_no_children():
    p = _bracket(_ledger({"engaged": True}))
    assert [(x.role, x.status) for x in p.legs] == [("entry", "blocked")]
    assert p.state == "rejected" and "kill switch" in p.legs[0].reason


def test_split_respects_the_size_cap():
    p = T.submit(
        _ledger(), "split", [T.Intent("jev", "NO", Decimal("13"))], now=NOW, max_clip=Decimal("4")
    )
    assert [x.requested for x in p.legs] == ["4", "4", "4", "1"]
    assert all(Decimal(x.notional) <= 4 for x in p.legs)


def test_live_mode_is_hard_disabled_by_the_gate():
    g = G.pre_trade(
        G.GateRequest(
            account="laya",
            path="single",
            value=Decimal(5),
            equity=L.SLEEVE,
            floor=Decimal(1),
            daily_pnl=Decimal(0),
            kill_engaged=False,
            mode="LIVE",
        ),
        G.risk_gate(L.ENVELOPE),
    )
    assert not g.allowed and g.code == "live_disabled" and G.LIVE_DISABLED in g.reason


@pytest.mark.parametrize(
    ("path", "intents", "clip", "legs"),
    [
        ("single", [T.Intent("laya", "YES", Decimal("5"))], None, 1),
        ("broadcast", T.broadcast(["laya", "jev", "coin"], "YES", Decimal("5")), None, 3),
        (
            "basket",
            [T.Intent("laya", "YES", Decimal("5")), T.Intent("coin", "NO", Decimal("6"))],
            None,
            2,
        ),
        ("split", [T.Intent("jev", "NO", Decimal("14"))], Decimal("5"), 3),
        ("bracket", T.broadcast(["laya", "coin"], "YES", Decimal("5")), None, 6),
    ],
)
def test_no_order_path_skips_the_gate(path, intents, clip, legs, monkeypatch):
    calls, real = [], G.pre_trade
    monkeypatch.setattr(G, "pre_trade", lambda req, risk: calls.append(req) or real(req, risk))
    lg = _ledger()
    calls.clear()  # the strategy replay above is covered by its own test
    px = {"take_profit": Decimal("0.70"), "stop": Decimal("0.30")} if path == "bracket" else {}
    p = T.submit(lg, path, intents, now=NOW, max_clip=clip, gate=SpyGate(), **px)
    assert len(p.legs) == legs and len(calls) == legs  # one pre_trade call per leg
    assert [r.account for r in calls] == [x.account for x in p.legs]
    assert {r.path for r in calls} == {path}


def test_every_strategy_decision_goes_through_the_one_gate(monkeypatch):
    calls, real = [], G.pre_trade
    monkeypatch.setattr(G, "pre_trade", lambda req, risk: calls.append(req) or real(req, risk))
    lg = _ledger()
    taken = [d for b in lg.books.values() for d in b.decisions if d.side is not None]
    assert taken and len(calls) == len(taken) and {r.path for r in calls} == {"strategy"}


def test_broadcast_to_three_accounts_is_three_independently_gated_legs(monkeypatch):
    calls, real = [], G.pre_trade
    monkeypatch.setattr(G, "pre_trade", lambda req, risk: calls.append(req) or real(req, risk))
    lg = _losing_laya()
    calls.clear()
    p = T.submit(lg, "broadcast", T.broadcast(["laya", "jev", "coin"], "NO", Decimal("5")), now=NOW)
    assert [r.account for r in calls] == ["laya", "jev", "coin"]
    # each leg is gated on its own account's P&L: laya's tripped envelope denies laya only
    assert {r.account: r.daily_pnl for r in calls}["laya"] <= -L.ENVELOPE.max_daily_loss
    assert [x.status for x in p.legs][0] == "blocked"


def test_journal_rebuilds_breakers_and_blotter_carries_parent_id(tmp_path):
    sd = str(tmp_path)
    for _ in range(4):
        T.submit(
            _ledger(),
            "split",
            [T.Intent("coin", "YES", Decimal("15"))],
            now=NOW,
            max_clip=Decimal("5"),
            state_dir=sd,
        )
    parents = T.load(sd)
    assert len(parents) == 4
    # 10 orders/minute per account: the 4th parent's last two clips are rate-denied
    assert [x.status for x in parents[-1].legs] == ["filled", "blocked", "blocked"]
    rows = B.orders(_ledger(), "coin", "blocked", None, tickets=T.blotter_rows(parents))
    assert len(rows) == 2 and all(r["parent_id"] == parents[-1].id for r in rows)
    assert all(o["parent_id"] is None for o in B.orders(_ledger(), "coin"))
    audit = (tmp_path / "risk-audit.jsonl").read_text().splitlines()
    assert len(audit) == 2 and json.loads(audit[0])["source"] == "breaker"


def test_page_shows_ticket_paper_note_bracket_live_disabled_and_legs():
    lg = _ledger()
    p = T.submit(
        lg, "broadcast", T.broadcast(["laya", "jev"], "YES", Decimal("5")), now=NOW, new_id=_ids()
    )
    html = render(
        lg, start="2026-10-06", now=NOW, tickets=[p], ticket_msg="broadcast p0: sent", view="trade"
    )
    assert 'aria-label="Order ticket · single / broadcast / basket / split / bracket"' in html
    assert "Ticket blotter" in html
    assert "paper only" in html and "0.50 mid + Kalshi taker fee" in html
    assert 'name="take_profit"' in html and 'name="stop"' in html and T.BRACKET_NOTE in html
    assert 'value="LIVE" disabled' in html and "no live venue approved" in html
    assert html.count("└ leg") == 2 and "broadcast p0: sent" in html


def test_ticket_endpoints(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from algobots.api.config import get_settings
    from algobots.api.main import app

    monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(tmp_path / "none.jsonl"))
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    get_settings.cache_clear()
    try:
        client = TestClient(app)
        r = client.post(
            "/demo/api/orders",
            json={
                "path": "broadcast",
                "accounts": ["laya", "jev", "coin"],
                "side": "YES",
                "notional": "5",
            },
        )
        assert r.status_code == 200 and r.json()["state"] == "sent" and len(r.json()["legs"]) == 3
        bad = client.post(
            "/demo/api/orders",
            json={
                "path": "single",
                "accounts": ["laya"],
                "side": "YES",
                "notional": "5",
                "mode": "LIVE",
            },
        )
        assert bad.status_code == 422 and "no live venue approved" in bad.json()["detail"]
        br = client.post(
            "/demo/api/orders",
            json={
                "path": "bracket",
                "accounts": ["laya"],
                "side": "YES",
                "notional": "5",
                "take_profit": "0.70",
                "stop": "0.30",
            },
        ).json()
        assert [x["status"] for x in br["legs"]] == ["filled", "working", "working"]
        cx = client.post(f"/demo/api/orders/{br['id']}/cancel").json()
        assert [x["status"] for x in cx["legs"]] == ["filled", "cancelled", "cancelled"]
        assert client.post("/demo/api/orders/nope/cancel").status_code == 404
        f = client.post(
            "/demo/orders",
            data={
                "path": "basket",
                "basket": "laya YES 5\ncoin NO 6",
                "ctx": "all",
                "side": "YES",
                "notional": "1",
            },
            follow_redirects=False,
        )
        assert f.status_code == 303 and "ticket=" in f.headers["location"]
        body = client.get("/demo/api/orders").json()
        tickets = [o for o in body["orders"] if o["source"] == "ticket"]
        assert len(tickets) == 8 and all(o["parent_id"] for o in tickets)
        assert [p["path"] for p in body["parents"]] == ["basket", "bracket", "broadcast"]
        page = client.get(f.headers["location"].split("#")[0])
        assert "basket" in page.text and "2/2 legs filled" in page.text
    finally:
        get_settings.cache_clear()
