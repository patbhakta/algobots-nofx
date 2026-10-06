"""ALG-3255 Nautilus paper worker: ledger FILLED decisions -> tagged paper orders."""

import json

import pytest

pytest.importorskip("nautilus_trader")

from algobots.demo import killswitch  # noqa: E402
from algobots.demo import ledger as L  # noqa: E402
from algobots.workers.paper import PaperWorker, ids  # noqa: E402

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
        assert w.step() == 6
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
        assert w.step() == 4
        assert w.strategy.submitted == 0
    finally:
        w.close()
