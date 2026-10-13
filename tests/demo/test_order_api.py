"""ALG-3263 (A10-4) contract tests: /demo/api/v1 executes on the paper workers.

Every write is gated by the ALG-3262 gate, then executed by that account's
real Nautilus paper worker (in-process here, same class the supervisor
spawns): the fill must carry the worker's trader / order-tag identity. A
worker that is down is a typed ``worker_unavailable`` — nothing falls back.
"""

import json
import os
from decimal import Decimal

import pytest

pytest.importorskip("nautilus_trader")

from algobots.api.config import get_settings  # noqa: E402
from algobots.demo import killswitch  # noqa: E402
from algobots.demo import orderapi as V  # noqa: E402
from algobots.demo import tickets as T  # noqa: E402
from algobots.engine.workers.lease import Lease  # noqa: E402
from algobots.engine.workers.paper import PaperWorker  # noqa: E402


class Rig:
    """Real per-account workers + the API client, on one throwaway state dir."""

    def __init__(self, tmp_path, monkeypatch, client) -> None:  # noqa: ANN001
        monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(tmp_path / "feed.jsonl"))
        monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
        (tmp_path / "feed.jsonl").write_text("")
        get_settings.cache_clear()
        self.tmp = tmp_path
        self.state_dir = str(tmp_path)
        self.workers: dict[str, PaperWorker] = {}
        self.client = client

    def up(self, account: str) -> PaperWorker:
        """A reconciled, heartbeat-fresh, lease-holding worker for ``account``."""
        if account not in self.workers:
            Lease(self.tmp, account).acquire()
            w = PaperWorker(account, self.tmp / "feed.jsonl", self.tmp, "2026-10-06", [])
            w.reconcile()
            w.heartbeat()
            self.workers[account] = w
        return self.workers[account]

    def drain(self) -> None:
        """Every worker claims its inbox, executes, and republishes its report."""
        for w in self.workers.values():
            w.drain_api_orders()
            w.heartbeat()

    def place(self, account: str, notional: str = "10", side: str = "YES"):
        return self.client.post(
            f"/demo/api/v1/{account}/orders/place", json={"side": side, "notional": notional}
        )

    def legs(self, account: str, status: str | None = None) -> list[dict]:
        q = {"status": status} if status else {}
        r = self.client.get(f"/demo/api/v1/{account}/orders", params=q)
        assert r.status_code == 200, r.text
        return r.json()["orders"]

    def close(self) -> None:
        for account, w in self.workers.items():
            w.close()
            Lease(self.tmp, account).release(os.getpid())
        get_settings.cache_clear()


@pytest.fixture
def rig(tmp_path, monkeypatch, client):
    r = Rig(tmp_path, monkeypatch, client)
    yield r
    r.close()


def _err(r):  # noqa: ANN001 — the typed error body or a test failure
    assert r.status_code >= 400, r.text
    body = r.json()
    return body.get("error") or body.get("detail")


# --- place + provable worker execution ------------------------------------------------------


def test_place_is_gated_then_executed_by_that_accounts_worker(rig):
    rig.up("laya")
    r = rig.place("laya")
    assert r.status_code == 200
    p = r.json()
    assert p["state"] == "sent"
    assert [(x["role"], x["status"]) for x in p["legs"]] == [("order", "submitted")]
    (leg,) = rig.legs("laya")
    assert leg["status"] == "submitted" and leg["worker_trader_id"] is None

    rig.drain()  # the worker claims the inbox and executes on its Nautilus engine
    (leg,) = rig.legs("laya")
    assert leg["status"] == "filled"
    assert leg["worker_trader_id"] == "PAPER-LAYA"  # ITS worker, provably
    assert leg["worker_order_id"] and "-LAYA-" in leg["worker_order_id"]  # order-tag ID
    assert leg["venue_account_id"] == "PAPER_LAYA-001" and leg["worker_trade_id"]
    assert leg["price"] == "0.50" and Decimal(leg["notional"]) == Decimal("10")
    assert Decimal(leg["fee"]) > 0

    rig.drain()  # idempotent: the claimed request never executes twice
    assert len(rig.legs("laya", "filled")) == 1


def test_fills_rebuild_the_rate_breakers(rig):
    rig.up("jev")
    for _ in range(4):  # 10 orders/minute per account: 12 clips trips the breaker
        r = rig.client.post(
            "/demo/api/v1/jev/orders/split",
            json={"side": "YES", "notional": "9", "max_clip": "3"},
        )
        assert r.status_code == 200
    rig.drain()
    legs = rig.legs("jev")
    assert len(legs) == 12
    blocked = [x for x in legs if x["status"] == "blocked"]
    assert len(blocked) == 2 and all(x["denial_code"] for x in blocked)


# --- typed denials -------------------------------------------------------------------------


def test_gated_denial_is_typed_and_queues_nothing(rig):
    rig.up("laya")
    killswitch.set_engaged(rig.state_dir, True, actor="test")
    r = rig.place("laya")
    assert r.status_code == 200
    p = r.json()
    assert p["state"] == "rejected"
    (leg,) = p["legs"]
    assert leg["status"] == "blocked" and leg["denial_code"] == "kill_switch"
    assert "kill switch" in leg["reason"]
    assert not V.inbox_path(rig.state_dir, "laya").exists()  # a denial never queues
    assert rig.legs("laya")[0]["denial_code"] == "kill_switch"


def test_live_mode_is_refused(rig):
    rig.up("laya")
    r = rig.client.post(
        "/demo/api/v1/laya/orders/place", json={"side": "YES", "notional": "5", "mode": "LIVE"}
    )
    assert r.status_code == 422 and "no live venue approved" in str(_err(r))


def test_unknown_or_ungranted_account_is_typed(rig):
    rig.up("laya")
    r = rig.client.post("/demo/api/v1/nope/orders/place", json={"side": "YES", "notional": "5"})
    assert r.status_code == 404


# --- worker_unavailable: typed, no fallback ------------------------------------------------


def test_worker_down_is_typed_and_journals_nothing(rig):
    r = rig.place("laya")  # no worker was ever started for laya
    err = _err(r)
    assert r.status_code == 503 and err["code"] == V.WORKER_UNAVAILABLE
    assert "laya" in err["reason"]
    assert T.load(rig.state_dir) == []  # refused before any order row exists
    for path in ("/demo/api/v1/laya/positions", "/demo/api/v1/laya/funds"):
        resp = rig.client.get(path)
        assert resp.status_code == 503
        assert resp.json()["error"]["code"] == V.WORKER_UNAVAILABLE


def test_worker_gone_stale_is_unavailable(rig):
    w = rig.up("laya")
    hb = w.status_path
    stale = json.loads(hb.read_text())
    stale["last_heartbeat"] -= 10_000  # hours older than the freshness window
    hb.write_text(json.dumps(stale))
    err = _err(rig.place("laya"))
    assert err["code"] == V.WORKER_UNAVAILABLE and "stale" in err["reason"]


# --- basket / split ------------------------------------------------------------------------


def test_basket_places_each_order_as_its_own_leg(rig):
    rig.up("laya")
    r = rig.client.post(
        "/demo/api/v1/laya/orders/basket",
        json={"orders": [{"side": "YES", "notional": "5"}, {"side": "NO", "notional": "6"}]},
    )
    assert r.status_code == 200
    assert [x["status"] for x in r.json()["legs"]] == ["submitted", "submitted"]
    rig.drain()
    fills = rig.legs("laya", "filled")
    assert [x["side"] for x in fills] == ["YES", "NO"]
    assert all(x["worker_trader_id"] == "PAPER-LAYA" for x in fills)


def test_split_chunks_under_the_max_clip(rig):
    rig.up("coin")
    r = rig.client.post(
        "/demo/api/v1/coin/orders/split",
        json={"side": "YES", "notional": "14", "max_clip": "5"},
    )
    assert r.status_code == 200
    assert [Decimal(x["requested"]) for x in r.json()["legs"]] == [
        Decimal("5"),
        Decimal("5"),
        Decimal("4"),
    ]
    rig.drain()
    assert len(rig.legs("coin", "filled")) == 3


# --- cancel / cancel-all -------------------------------------------------------------------


def test_cancel_before_execution_beats_the_worker(rig):
    rig.up("laya")
    p = rig.place("laya").json()
    r = rig.client.post(f"/demo/api/v1/orders/{p['id']}/cancel")
    assert r.status_code == 200
    (leg,) = r.json()["legs"]
    assert leg["status"] == "cancelled" and T.CANCEL_BEFORE_RUN in leg["reason"]
    rig.drain()  # the worker drops a cancelled request; fills are the only finals
    assert rig.legs("laya")[0]["status"] == "cancelled"
    assert rig.client.post("/demo/api/v1/orders/nope/cancel").status_code == 404


def test_cancel_all_is_scoped_to_one_account(rig):
    rig.up("laya")
    rig.up("jev")
    on_laya = rig.place("laya").json()
    on_jev = rig.place("jev").json()

    r = rig.client.post("/demo/api/v1/laya/orders/cancel-all")
    assert r.status_code == 200
    assert r.json()["cancelled"] == [
        {"parent_id": on_laya["id"], "path": "single", "cancelled": 1}
    ]

    assert [x["status"] for x in rig.legs("laya")] == ["cancelled"]  # only laya's
    assert [x["status"] for x in rig.legs("jev")] == ["submitted"]  # jev untouched
    rig.drain()
    assert rig.legs("laya", "filled") == []
    (fill,) = rig.legs("jev", "filled")
    assert fill["worker_trader_id"] == "PAPER-JEV" and on_jev["id"] == fill["parent_id"]


# --- close-position / books ----------------------------------------------------------------


def test_close_position_exits_the_workers_open_position(rig):
    rig.up("laya")
    rig.place("laya")
    rig.drain()
    (pos,) = rig.client.get("/demo/api/v1/laya/positions").json()["positions"]
    assert pos["side"] == "LONG" and Decimal(pos["qty"]) == 20 and pos["symbol"].endswith("-YES")

    r = rig.client.post("/demo/api/v1/laya/positions/close", json={})
    assert r.status_code == 200
    close = r.json()["closes"]
    assert len(close) == 1 and close[0]["legs"][0]["kind"] == "exit"
    rig.drain()

    assert rig.client.get("/demo/api/v1/laya/positions").json()["positions"] == []
    trades = rig.client.get("/demo/api/v1/laya/trades").json()["trades"]
    assert [t["kind"] for t in trades] == ["exit", "entry"]
    assert {t["trader_id"] for t in trades} == {"PAPER-LAYA"}  # both legs: same worker

    r = rig.client.post("/demo/api/v1/laya/positions/close", json={})
    assert r.status_code == 404 and _err(r)["code"] == V.NO_OPEN_POSITION

    r = rig.client.post("/demo/api/v1/laya/positions/close", json={"instrument": "nope-YES"})
    assert r.status_code == 404 and _err(r)["code"] == V.NO_OPEN_POSITION


def test_funds_come_from_the_worker(rig):
    w = rig.up("laya")
    rig.place("laya")
    rig.drain()
    f = rig.client.get("/demo/api/v1/laya/funds").json()["funds"]
    assert f["currency"] == "USD"
    assert Decimal(f["allocated"]) == Decimal("100")
    assert Decimal(f["api_open_notional"]) == Decimal("10")
    assert Decimal(f["api_fees_paid"]) > 0
    # the venue debited the buy; P&L truth stays with the ledger
    assert Decimal(f["venue_balance"]) == Decimal("90")
    assert f["open_positions"] == 1
    hb = w.heartbeat()
    assert hb["api_orders_filled"] == 1
    assert Decimal(hb["report"]["funds"]["api_open_notional"]) == Decimal("10")


# --- the terminal ticket shares this path --------------------------------------------------


def test_terminal_ticket_endpoint_routes_through_the_workers(rig):
    rig.up("laya")
    rig.up("jev")
    r = rig.client.post(
        "/demo/api/orders",
        json={"path": "broadcast", "accounts": ["laya", "jev"], "side": "YES", "notional": "5"},
    )
    assert r.status_code == 200
    assert [x["status"] for x in r.json()["legs"]] == ["submitted", "submitted"]
    rig.drain()
    assert {x["worker_trader_id"] for x in rig.legs("laya", "filled")} == {"PAPER-LAYA"}
    assert {x["worker_trader_id"] for x in rig.legs("jev", "filled")} == {"PAPER-JEV"}


def test_trade_book_lists_worker_executed_fills(rig):
    rig.up("coin")
    rig.place("coin", notional="7")
    rig.drain()
    (t,) = rig.client.get("/demo/api/v1/coin/trades").json()["trades"]
    assert Decimal(t["qty"]) == 14 and t["price"] == "0.50"
    assert t["trader_id"] == "PAPER-COIN" and t["trade_id"] and t["venue_account_id"]
