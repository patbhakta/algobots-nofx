"""Order ticket (ALG-3265): four paths, one risk gate on every leg, privileged exits."""

import json
from decimal import Decimal

import pytest

from algobots.demo import blotter as B
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


def test_entry_is_clamped_to_max_order_value_and_bracket_is_refused_with_reason():
    p = T.submit(_ledger(), "single", [T.Intent("laya", "YES", Decimal("40"))], now=NOW)
    assert p.legs[0].notional == str(L.ENVELOPE.max_order_value) and p.legs[0].clamped
    with pytest.raises(T.TicketError, match="unsupported for KXBTC15M binary 15m"):
        T.submit(
            _ledger(), "single", [T.Intent("laya", "YES", Decimal("5"))], now=NOW, bracket=True
        )


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
    ],
)
def test_no_order_path_skips_the_gate(path, intents, clip, legs):
    gate = SpyGate()
    p = T.submit(_ledger(), path, intents, now=NOW, max_clip=clip, gate=gate)
    assert len(p.legs) == legs and len(gate.seen) == legs  # one gate call per leg
    assert gate.seen == [x.account for x in p.legs]


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


def test_page_shows_ticket_paper_note_bracket_reason_and_legs():
    lg = _ledger()
    p = T.submit(
        lg, "broadcast", T.broadcast(["laya", "jev"], "YES", Decimal("5")), now=NOW, new_id=_ids()
    )
    html = render(lg, start="2026-10-06", now=NOW, tickets=[p], ticket_msg="broadcast p0: sent")
    assert 'aria-label="Order ticket · single / broadcast / basket / split"' in html
    assert "Ticket blotter" in html
    assert "paper only" in html and "0.50 mid + Kalshi taker fee" in html
    assert 'name="bracket" disabled' in html and "unsupported for KXBTC15M binary 15m" in html
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
                "bracket": True,
            },
        )
        assert bad.status_code == 422 and "unsupported" in bad.json()["detail"]
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
        assert len(tickets) == 5 and all(o["parent_id"] for o in tickets)
        assert [p["path"] for p in body["parents"]] == ["basket", "broadcast"]
        page = client.get(f.headers["location"].split("#")[0])
        assert "basket" in page.text and "2/2 legs filled" in page.text
    finally:
        get_settings.cache_clear()
