"""ALG-3340 bridge-channel mirror tests (stdlib only, no Nautilus needed).

``ALGOBOTS_BRIDGE_DIR`` set -> intents, fills and stats land in the shared
channel; unset -> nothing is written anywhere. A channel write failure
(unwritable root) must never raise into the trading path.
"""

import json
from pathlib import Path

from algobots.engine.workers import bridge


def _lines(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text().splitlines()]


def test_mirrors_land_in_the_channel_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("ALGOBOTS_BRIDGE_DIR", str(tmp_path))
    bridge.mirror_intent({"leg_id": "L1", "parent_id": "P1", "notional": "10"})
    bridge.mirror_fill({"client_order_id": "O-1", "source": "api"})
    bridge.bump_stats("/demo/api/v1/laya/orders/place", 12.5, 200)
    bridge.bump_stats("/demo/api/v1/laya/orders/place", 30.0, 200)

    (intent,) = _lines(tmp_path / "intents" / "intents.jsonl")
    assert intent["leg_id"] == "L1" and intent["parent_id"] == "P1"
    assert intent["mirrored_ts"] > 0  # the mirror stamps its own receipt time

    (fill,) = _lines(tmp_path / "fills" / "fills.jsonl")
    assert fill["client_order_id"] == "O-1" and fill["source"] == "api"

    stats = json.loads((tmp_path / "stats.json").read_text())
    e = stats["calls"]["/demo/api/v1/laya/orders/place"]
    assert e["count"] == 2 and e["max_ms"] == 30.0 and e["last_status"] == 200
    assert stats["updated_ts"] > 0


def test_unset_bridge_dir_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.delenv("ALGOBOTS_BRIDGE_DIR", raising=False)
    bridge.mirror_intent({"leg_id": "L3"})
    bridge.mirror_fill({"client_order_id": "O-3"})
    bridge.bump_stats("/demo/api/v1/laya/trades", 1.0, 200)
    assert not any(tmp_path.iterdir())


def test_channel_failure_never_raises(tmp_path, monkeypatch):
    root = tmp_path / "bridge"  # a FILE where the channel root should be
    root.write_text("not a dir")
    monkeypatch.setenv("ALGOBOTS_BRIDGE_DIR", str(root))
    bridge.mirror_intent({"leg_id": "L4"})  # must swallow, not raise
    bridge.mirror_fill({"client_order_id": "O-4"})
    bridge.bump_stats("/demo/api/v1/laya/trades", 1.0, 200)
