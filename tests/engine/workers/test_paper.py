"""ALG-3255/3258 Nautilus paper worker: ledger FILLED decisions -> tagged paper orders."""

import json

import pytest

pytest.importorskip("nautilus_trader")

from algobots.demo import killswitch  # noqa: E402
from algobots.demo import ledger as L  # noqa: E402
from algobots.engine.workers.paper import PaperWorker, ids  # noqa: E402

T0 = 1791244800.0  # 2026-10-06T00:00Z


def _rows(n: int, start: int = 0) -> list[str]:
    return [
        json.dumps(
            {
                "event": f"KXBTC15M-26OCT06{i:04d}",
                "strike": 85000,
                "outcome": i % 2,
                "ts": T0 + i * 900,
                "p": 0.6 if i % 3 else 0.505,  # every 3rd interval: Laya abstains
                "conf": 0.1,
                "jev_p": 0.6,
                "jev_conf": 0.5,
                "jev_choice": "down" if i % 2 else "up",
            }
        )
        for i in range(start, start + n)
    ]


def _worker(tmp_path, account: str) -> PaperWorker:
    return PaperWorker(account, tmp_path / "feed.jsonl", tmp_path, "2026-10-06", [])


def test_ids_are_unique_per_account():
    all_ids = [ids(a) for a in L.STRATEGIES]
    for key in ("trader_id", "strategy_id", "order_id_tag", "venue", "account_id"):
        assert len({i[key] for i in all_ids}) == len(L.STRATEGIES)


def test_worker_submits_exactly_the_ledger_fills_and_only_new_ones(tmp_path):
    feed = tmp_path / "feed.jsonl"
    feed.write_text("\n".join(_rows(6)) + "\n")
    w = _worker(tmp_path, "laya")
    try:
        assert w.reconcile() == 4  # first start: the ledger's fills, restored
        fills = L.build(L.load_rows(feed)).books["laya"].fills
        assert w.strategy.submitted == w.strategy.filled == len(fills) == 4
        hb = w.heartbeat()
        assert hb["venue_account_id"] == "PAPER_LAYA-001" == hb["account_id"]
        assert hb["trader_id"] == "PAPER-LAYA" and hb["ready_at"] is not None
        assert "-LAYA-" in hb["last_order"]["client_order_id"]
        assert hb["last_order"]["instrument"].endswith(".PAPER_LAYA")
        orders = w.engine.cache.orders()
        assert all("acct:laya" in o.tags for o in orders)

        assert w.step() == 0  # nothing new -> nothing resubmitted
        assert w.strategy.submitted == 4
        feed.write_text(feed.read_text() + "\n".join(_rows(2, start=6)) + "\n")
        assert w.step() == 2
        assert w.strategy.submitted == len(L.build(L.load_rows(feed)).books["laya"].fills)
    finally:
        w.close()


def test_kill_switch_blocks_worker_orders(tmp_path):
    (tmp_path / "feed.jsonl").write_text("\n".join(_rows(4)) + "\n")
    killswitch.set_engaged(str(tmp_path), True, actor="test", now=T0 - 1)
    w = _worker(tmp_path, "coin")
    try:
        assert w.reconcile() == 0
        assert w.step() == 0
        assert w.strategy.submitted == 0
    finally:
        w.close()


def test_crash_restart_is_entry_frozen_until_reconciled(tmp_path):
    """AC4: a restarted worker submits nothing until it has reconciled."""
    feed = tmp_path / "feed.jsonl"
    feed.write_text("\n".join(_rows(6)) + "\n")
    first = _worker(tmp_path, "laya")
    first.reconcile()
    assert first.strategy.submitted == 4
    first.close()  # the "crash": everything in memory is gone

    feed.write_text(feed.read_text() + "\n".join(_rows(3, start=6)) + "\n")
    w = _worker(tmp_path, "laya")
    try:
        assert w.heartbeat()["phase"] == "reconciling" and not w.reconciled
        w.step()  # new FILLED intervals arrive before reconcile
        assert w.strategy.submitted == 0 and w.strategy.rejected_frozen > 0
        assert w.engine.cache.orders() == []
        rejected = w.strategy.rejected_frozen

        fills = len(L.build(L.load_rows(feed)).books["laya"].fills)
        assert w.reconcile() == fills  # refused intervals are restored, not lost
        hb = w.heartbeat()
        assert hb["phase"] == "ready" and hb["reconciled"] is True
        assert hb["orders_restored"] == fills and hb["orders_rejected_frozen"] == rejected

        feed.write_text(feed.read_text() + "\n".join(_rows(2, start=9)) + "\n")
        w.step()
        total = len(L.build(L.load_rows(feed)).books["laya"].fills)
        assert w.strategy.submitted == total and w.strategy.restored == fills
        assert w.strategy.rejected_frozen == rejected  # no refusals once reconciled
    finally:
        w.close()


def test_every_fill_mirrors_to_the_bridge_channel(tmp_path, monkeypatch):
    """ALG-3340: each Nautilus OrderFilled lands in fills/fills.jsonl, tagged."""
    import json as _json


    channel = tmp_path / "bridge"
    monkeypatch.setenv("ALGOBOTS_BRIDGE_DIR", str(channel))
    (tmp_path / "feed.jsonl").write_text("\n".join(_rows(6)) + "\n")
    w = _worker(tmp_path, "laya")
    try:
        restored = w.reconcile()
        mirrored = [
            _json.loads(x)
            for x in (channel / "fills" / "fills.jsonl").read_text().splitlines()
        ]
        assert len(mirrored) == restored == 4
        assert all(m["source"] == "decision" for m in mirrored)
        assert {m["client_order_id"] for m in mirrored} == {
            str(o.client_order_id) for o in w.engine.cache.orders()
        }
    finally:
        w.close()
