"""ALG-3340 end-to-end: NoFX-shaped intent -> admission -> file channel ->
the account's real Nautilus paper worker -> fills JSONL -> read-back views.

Same shape as the ALG-3263 order-API tests: in-process workers (the same
class the supervisor spawns), real gate, real venue. No order path bypasses
the engine — there is no simulator to fall back to anywhere in this flow.
"""

from __future__ import annotations

import json
import os
from decimal import Decimal

import pytest

pytest.importorskip("nautilus_trader")

from algobots.api.config import get_settings  # noqa: E402
from algobots.demo import killswitch  # noqa: E402
from algobots.engine.workers.lease import Lease  # noqa: E402
from algobots.engine.workers.paper import PaperWorker  # noqa: E402


class Rig:
    """Real per-account bridge-aware workers + the API client, one throwaway state."""

    def __init__(self, tmp_path, monkeypatch, client, grants="laya,jev,coin") -> None:
        monkeypatch.setenv("ALGOBOTS_DEMO_FEED_PATH", str(tmp_path / "feed.jsonl"))
        monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
        monkeypatch.setenv("ALGOBOTS_BRIDGE_DIR", str(tmp_path / "bridge"))
        monkeypatch.setenv("ALGOBOTS_DEMO_ACCOUNT_GRANTS", grants)
        (tmp_path / "feed.jsonl").write_text("")
        get_settings.cache_clear()
        self.tmp = tmp_path
        self.bridge = tmp_path / "bridge"
        self.state_dir = str(tmp_path)
        self.workers: dict[str, PaperWorker] = {}
        self.client = client

    def up(self, account: str) -> PaperWorker:
        if account not in self.workers:
            Lease(self.tmp, account).acquire()
            w = PaperWorker(
                account, self.tmp / "feed.jsonl", self.tmp, "2026-10-06", [],
                bridge_dir=self.bridge,
            )
            w.reconcile()
            w.heartbeat()
            self.workers[account] = w
        return self.workers[account]

    def drain(self) -> None:
        for w in self.workers.values():
            w.drain_api_orders()
            w.drain_bridge_intents()
            w.heartbeat()

    def post(self, **body):  # noqa: ANN003 — the NoFX-shaped wire payload
        return self.client.post("/bridge/intents", json=body)

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


def _err(r):  # noqa: ANN001 — the typed error body, or a test failure
    assert r.status_code >= 400, r.text
    body = r.json()
    return body.get("error") or body.get("detail")


# --- the flow: intent -> worker's Nautilus engine -> fills JSONL -> views ---------------------


def test_intent_fills_on_the_account_worker_and_mirrors_to_the_channel(rig):
    rig.up("laya")
    r = rig.post(account="laya", side="buy", qty=10)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["status"] == "admitted" and out["venue"] == "PAPER_LAYA"
    assert out["notional"] == "5.00"

    intent_file = rig.bridge / "intents" / f"{out['intent_id']}.json"
    assert intent_file.exists()  # the channel IS the handoff

    rig.drain()
    fills = json.loads((rig.bridge / "fills" / "laya.jsonl").read_text().splitlines()[0])
    assert fills["intent_id"] == out["intent_id"]
    assert fills["trader_id"] == "PAPER-LAYA"  # ITS worker, provably
    assert fills["venue_account_id"] == "PAPER_LAYA-001" and fills["trade_id"]
    assert Decimal(fills["qty"]) == 10 and fills["px"] == "0.50"

    done = json.loads((rig.bridge / "done" / f"{out['intent_id']}.json").read_text())
    assert done["status"] == "filled" and done["fill"]["px"] == "0.50"

    got = rig.client.get("/bridge/fills", params={"account": "laya"})
    assert got.status_code == 200 and got.json()["fills"][0]["intent_id"] == out["intent_id"]

    pos = rig.client.get("/bridge/positions/laya")
    assert pos.status_code == 200, pos.text
    (position,) = pos.json()["positions"]
    assert position["venue"] == "PAPER_LAYA" and Decimal(position["qty"]) == 10

    st = rig.client.get("/bridge/intents/" + out["intent_id"]).json()
    assert st["state"] == "done" and st["intent"]["status"] == "filled"


def test_drain_is_idempotent_intent_never_fills_twice(rig):
    rig.up("laya")
    out = rig.post(account="laya", side="buy", qty=5).json()
    rig.drain()
    rig.drain()  # the claimed intent is gone from intents/; replay only on crash
    lines = (rig.bridge / "fills" / "laya.jsonl").read_text().splitlines()
    assert len(lines) == 1 and json.loads(lines[0])["intent_id"] == out["intent_id"]


def test_order_value_clamp_sizes_the_intent_not_the_refusal(rig):
    rig.up("laya")
    out = rig.post(account="laya", side="buy", qty=100).json()  # 50 USD at 50c
    assert out["qty"] == 30 and out["notional"] == "15.00"  # envelope max order 15


def test_stats_counts_traffic_and_channel(rig):
    rig.up("laya")
    rig.post(account="laya", side="buy", qty=2)
    rig.client.get("/bridge/fills", params={"account": "laya"})
    rig.drain()
    stats = rig.client.get("/bridge/stats").json()
    ep = stats["endpoints"]["POST /bridge/intents"]
    assert ep["count"] >= 1 and ep["latency_ms"]["p50"] is not None  # registry is process-wide
    assert stats["channel"]["intents_done"] == 1 and stats["channel"]["fills_recorded"] == 1


def test_sell_intent_exits_and_closes_the_position(rig):
    rig.up("laya")
    symbol = rig.post(account="laya", side="buy", qty=4).json()["symbol"]
    rig.drain()
    out = rig.post(account="laya", side="sell", qty=4, symbol=symbol).json()
    assert out["kind"] == "exit"
    rig.drain()
    pos = rig.client.get("/bridge/positions/laya").json()["positions"]
    assert pos == []  # round trip: venue flat again
    assert len(rig.client.get("/bridge/fills", params={"account": "laya"}).json()["fills"]) == 2


# --- admission refusals: typed, and nothing is written ---------------------------------------


def test_refusals_are_typed_and_write_nothing(rig):
    rig.up("laya")
    cases = [
        ({"account": "nope", "side": "buy", "qty": 1}, 404, None),
        ({"account": "jev", "side": "buy", "qty": 1}, 503, "worker_unavailable"),
        ({"account": "laya", "side": "long", "qty": 1}, 422, "invalid_side"),
        ({"account": "laya", "side": "buy", "qty": 0}, 422, "invalid_qty"),
        ({"account": "laya", "side": "buy", "qty": 1, "symbol": "NOPE"}, 422, "invalid_symbol"),
        ({"account": "laya", "side": "buy", "qty": 1, "mode": "LIVE"}, 403, "live_disabled"),
        (
            {"account": "laya", "side": "buy", "qty": 1, "ts_utc": "yesterday"},
            422,
            "invalid_ts_utc",
        ),
    ]
    for body, status, code in cases:
        r = rig.post(**body)
        assert r.status_code == status, (body, r.text)
        if code:
            assert _err(r)["code"] == code, body
    assert not (rig.bridge / "intents").exists() or not list(
        (rig.bridge / "intents").glob("*.json")
    )  # a refused intent never reaches the channel


def test_ungranted_account_is_forbidden(rig, monkeypatch):
    rig.up("laya")
    assert rig.post(account="laya", side="buy", qty=1).status_code == 201
    monkeypatch.setenv("ALGOBOTS_DEMO_ACCOUNT_GRANTS", "jev")  # laya loses the grant
    get_settings.cache_clear()
    try:
        assert rig.client.get("/bridge/fills", params={"account": "laya"}).status_code == 403
        assert rig.client.get("/bridge/positions/laya").status_code == 403
        assert rig.post(account="laya", side="buy", qty=1).status_code == 403
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_kill_switch_blocks_bridge_entries(rig):
    rig.up("laya")
    killswitch.set_engaged(rig.state_dir, True, actor="test")
    r = rig.post(account="laya", side="buy", qty=1)
    assert r.status_code == 403 and _err(r)["code"] == "kill_switch"
    killswitch.set_engaged(rig.state_dir, False, actor="test")


def test_bridge_disabled_answers_typed_503(tmp_path, monkeypatch, client):
    monkeypatch.setenv("ALGOBOTS_DEMO_STATE_DIR", str(tmp_path))
    monkeypatch.setenv("ALGOBOTS_BRIDGE_DIR", "")
    get_settings.cache_clear()
    r = client.get("/bridge/fills", params={"account": "laya"})
    assert r.status_code == 503 and r.json()["detail"]["code"] == "bridge_disabled"
    get_settings.cache_clear()


def test_healthz_stays_up_alongside_the_bridge(rig):  # the NoFX probe from ms2 must keep working
    assert rig.client.get("/healthz").status_code == 200
