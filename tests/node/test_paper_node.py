"""ALG-3405: the rc6 paper node's wiring that does not need the engine.

The node itself runs only where ``nautilus_trader`` 2.0.0rc6 is installed (the
``nautilus-node`` image); ``scripts/rc6_node_smoke.py`` and the capture in
``tests/gateway/fixtures/rc6_event_streams.json`` are its end-to-end evidence.
What runs everywhere is that importing it costs nothing and that its names
line up with the gateway's: the command stream it reads and the trader id its
events are keyed under.
"""

from __future__ import annotations

from decimal import Decimal

from algobots.node import paper_node
from algobots.node.command_stream import stream_key
from algobots.node.event_egress import events_glob


def test_defaults_name_one_paper_node_on_the_sandbox_venue():
    s = paper_node.settings({})
    assert (s.node, s.venue, s.nautilus_account_id, s.symbol) == (
        "nautilus-paper",
        "SIM",
        "SIM-001",
        "EUR/USD.SIM",
    )
    assert s.starting_balance == Decimal("100000")
    assert paper_node.NAUTILUS_PIN == "2.0.0rc6"


def test_the_node_reads_the_stream_the_gateway_writes_and_keys_events_by_trader():
    s = paper_node.settings({"ALGOBOTS_NODE": "nautilus-laya", "REDIS_PORT": "6380"})
    assert stream_key(s.node) == "algobots:cmd:nautilus-laya"
    assert s.trader_id == "NAUTILUS-LAYA"
    assert events_glob(s.trader_id) == "trader-NAUTILUS-LAYA:algobots:events.*"
    assert s.redis_port == 6380


def test_the_node_replays_the_image_catalog_by_default():
    """ALG-3406: recorded quotes, not the random walk, unless asked for."""
    s = paper_node.settings({})
    assert s.feed == "replay"
    assert s.replay_path == "/catalog/data/quote_tick/EURUSD.SIM/part-0.parquet"
    assert (s.replay_speed, s.replay_max_gap_s, s.feed_signal_s) == (1.0, 2.0, 1.0)
    assert paper_node.settings({"ALGOBOTS_FEED": "synthetic"}).feed == "synthetic"
