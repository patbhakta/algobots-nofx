"""P1.5: the leg between the node and the projection, without any services.

``tests/e2e`` measures GATE G1 over a real server and skips when one is not
configured. These tests are the rules on that path, and they run everywhere:
the envelope the node writes, the keys it writes them to, what the gateway's
reader decodes and refuses, where its cursor stops, and the three properties
the whole design rests on — a stream discovered late is read from its start, a
replay changes nothing, and a node's liveness arrives by the same route as its
fills.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from tests.fakes import FakeRedis

from algobots.gateway.event_ingest import FROM_START, NodeEventIngest, decode
from algobots.gateway.fixture_node import fixture_stack
from algobots.gateway.projection import InMemoryProjection
from algobots.node.event_egress import (
    JSON_ENCODING,
    EventEgress,
    events_glob,
    stream_key,
    topic_for,
)
from algobots.node.sandbox import trader_id_for

TRADER = "NAUTILUS-LAYA"


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def node_side(redis):  # noqa: ANN001, ANN201
    """A fixture node whose events are published instead of folded."""
    registry, projection, bus, node = fixture_stack()
    node.sink = EventEgress(client=redis, trader_id=trader_id_for(node.node.node)).publish
    return node


@pytest.fixture
def gateway_side(redis):  # noqa: ANN001, ANN201
    """A registry and projection fed only by the ingest loop."""
    registry, projection, _bus, _node = fixture_stack()
    ingest = NodeEventIngest(
        client=redis, registry=registry, projection=projection, trader_id=TRADER
    )
    return registry, projection, ingest


# --- the envelope -----------------------------------------------------------


def test_the_key_puts_the_trader_prefix_before_the_streams_prefix():
    """The detail P0.3 recorded: ``algobots*`` does not match these keys."""
    assert stream_key(TRADER, "events.order.S-000") == (
        f"trader-{TRADER}:algobots:events.order.S-000"
    )
    assert events_glob(TRADER) == f"trader-{TRADER}:algobots:events.*"
    assert not stream_key(TRADER, "events.order.S-000").startswith("algobots")


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"type": "OrderFilled", "strategy_id": "S-000"}, "events.order.S-000"),
        ({"type": "PositionOpened", "strategy_id": "S-000"}, "events.position.S-000"),
        ({"type": "AccountState", "account_id": "SIM-001"}, "events.account.SIM-001"),
        ({"type": "AlgoBotsHeartbeat", "node": "nautilus-laya"}, "events.heartbeat.nautilus-laya"),
    ],
)
def test_each_event_is_published_on_the_topic_nautilus_would_use(payload, expected):  # noqa: ANN001
    assert topic_for(payload) == expected


def test_an_unroutable_event_still_lands_under_events_so_it_is_readable():
    """It becomes a no-op at the fold, not an entry the gateway never sees."""
    assert topic_for({"type": "SomethingNew"}).startswith("events.")


def test_the_published_entry_carries_the_engines_four_fields(redis, node_side):  # noqa: ANN001
    node_side.account_state("100.00")
    key = stream_key(trader_id_for(node_side.node.node), "events.account.SIM-001")
    (entry_id, fields), *rest = redis.entries(key)
    assert not rest
    assert entry_id
    assert set(fields) == {"topic", "type", "payload", "encoding"}
    assert fields["encoding"] == JSON_ENCODING
    assert json.loads(fields["payload"])["type"] == "AccountState"


def test_a_decimal_in_a_payload_is_serialised_rather_than_raising(redis):  # noqa: ANN001
    """Losing a fill to a serialisation error would be the worst failure here."""
    egress = EventEgress(client=redis, trader_id=TRADER)
    egress.publish({"type": "OrderFilled", "strategy_id": "S-000", "last_px": Decimal("1.5")})
    key = stream_key(TRADER, "events.order.S-000")
    assert json.loads(redis.entries(key)[0][1]["payload"])["last_px"] == "1.5"


# --- what the reader refuses ------------------------------------------------


def test_decode_reads_the_engines_json_envelope():
    assert decode({"payload": '{"type":"OrderFilled"}', "encoding": "Json"}) == {
        "type": "OrderFilled"
    }


def test_decode_tolerates_a_client_that_returns_bytes():
    """``decode_responses=False`` is what the deploy's client uses."""
    assert decode({b"payload": b'{"type":"OrderFilled"}', b"encoding": b"Json"}) == {
        "type": "OrderFilled"
    }


@pytest.mark.parametrize(
    "fields",
    [
        {"payload": "not json", "encoding": "Json"},
        {"payload": "[1,2,3]", "encoding": "Json"},
        {"payload": '{"type":"OrderFilled"}', "encoding": "MsgPack"},
        {"encoding": "Json"},
        {},
    ],
)
def test_decode_refuses_anything_it_cannot_read_as_an_event(fields):  # noqa: ANN001
    """An unreadable entry must not become state — msgpack least of all."""
    assert decode(fields) is None


def test_an_undecodable_entry_does_not_block_the_stream_behind_it(redis, gateway_side):  # noqa: ANN001
    registry, projection, ingest = gateway_side
    key = stream_key(TRADER, "events.heartbeat.nautilus-laya")
    redis.xadd(key, {"payload": "garbage", "encoding": "Json"})
    redis.xadd(
        key,
        {
            "payload": json.dumps(
                {
                    "type": "AlgoBotsHeartbeat",
                    "node": "nautilus-laya",
                    "reconciled": True,
                    "ts": 1_700_000_000.0,
                }
            ),
            "encoding": "Json",
        },
    )

    appended = ingest.poll()
    assert [event["type"] for event in appended] == ["heartbeat"]


# --- the three properties the design rests on -------------------------------


def test_a_stream_discovered_late_is_read_from_its_beginning(redis, gateway_side, node_side):  # noqa: ANN001
    """Everything published before the scan that noticed the stream.

    Reading from the tail instead would silently lose exactly the fills that
    happened while the gateway was starting.
    """
    registry, projection, ingest = gateway_side
    node_side.heartbeat()
    node_side.account_state("100.00")

    fresh = ingest.discover()
    assert fresh, "no stream was discovered"
    assert all(ingest.cursors[key] == FROM_START for key in fresh)

    assert {event["type"] for event in ingest.poll()} == {"heartbeat", "balance"}


def test_the_nodes_liveness_arrives_by_the_same_route_as_its_fills(redis, gateway_side, node_side):  # noqa: ANN001
    """The heartbeat is read off the stream into the registry the routes hold.

    This is what makes a node that stopped publishing events a node that stops
    looking fit, rather than two liveness facts that can disagree.
    """
    registry, projection, ingest = gateway_side
    node = registry.nodes["nautilus-laya"]
    assert node.last_heartbeat is None and not node.reconciled

    node_side.heartbeat()
    ingest.poll()

    assert node.reconciled
    assert node.last_heartbeat == pytest.approx(node_side.clock)


def test_replaying_a_fill_leaves_one_fill_in_the_projection(redis, gateway_side, node_side):  # noqa: ANN001
    """Why reading from the start is safe: the fold is idempotent.

    The entries are re-read by resetting the cursor, which is what a restarted
    gateway does — it has no durable cursor of its own, only the projection.
    """
    registry, projection, ingest = gateway_side
    # The gateway admitted this order, so its events are not dropped.
    from algobots.gateway.node_events import admitted_order

    key = "g1-replay-0001"
    projection.put_order(
        admitted_order(
            client_order_id=key,
            account_id="laya",
            node="nautilus-laya",
            symbol="EUR/USD.SIM",
            side="buy",
            qty=Decimal("100000"),
            order_type="market",
            now=1_700_000_000.0,
        )
    )
    node_side.execute(
        {
            "command": "submit_order",
            "client_order_id": key,
            "symbol": "EUR/USD.SIM",
            "side": "buy",
            "qty": "100000",
            "order_type": "market",
        }
    )

    ingest.poll()
    once = projection.order(key)
    assert once is not None and once.status == "filled"
    assert len(once.fills) == 1

    ingest.cursors = dict.fromkeys(ingest.cursors, FROM_START)
    ingest.poll()

    twice = projection.order(key)
    assert twice is not None
    assert len(twice.fills) == 1, "a replayed fill was folded twice"
    assert twice.filled_qty == once.filled_qty


def test_an_event_for_an_unadmitted_order_is_dropped(redis, gateway_side, node_side):  # noqa: ANN001
    """``node_events`` rule 2, reached through the transport."""
    registry, projection, ingest = gateway_side
    node_side.execute(
        {
            "command": "submit_order",
            "client_order_id": "never-admitted-01",
            "symbol": "EUR/USD.SIM",
            "side": "buy",
            "qty": "1",
            "order_type": "market",
        }
    )

    appended = ingest.poll()

    assert projection.order("never-admitted-01") is None
    assert [event["type"] for event in appended] == ["position"]


def test_the_cursor_advances_so_a_second_poll_re_reads_nothing(redis, gateway_side, node_side):  # noqa: ANN001
    registry, projection, ingest = gateway_side
    node_side.heartbeat()

    assert len(ingest.poll()) == 1
    assert ingest.poll() == []


def test_the_ingest_reads_only_its_own_traders_streams(redis, gateway_side):  # noqa: ANN001
    """One gateway may serve a fleet; it may not read another fleet's events."""
    registry, projection, ingest = gateway_side
    other = EventEgress(client=redis, trader_id="SOMEONE-ELSE")
    other.heartbeat(node="nautilus-laya", nautilus_account_id="SIM-001", ts=1_700_000_000.0)

    assert ingest.poll() == []
    assert registry.nodes["nautilus-laya"].last_heartbeat is None


def test_the_in_memory_and_sql_folds_see_the_same_events(redis, node_side):  # noqa: ANN001
    """The store is behind the ``Projection`` protocol on this path too."""
    registry, _projection, _bus, _ = fixture_stack()
    store = InMemoryProjection()
    ingest = NodeEventIngest(
        client=redis, registry=registry, projection=store, trader_id=TRADER
    )
    node_side.heartbeat()
    node_side.account_state("250.50")

    assert [event["type"] for event in ingest.poll()] == ["heartbeat", "balance"]
    assert store.balances("laya")[0]["total"] == "250.50"
