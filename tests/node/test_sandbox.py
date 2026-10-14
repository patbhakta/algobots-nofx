"""P1.5: the node the gate drives, assembled over a fake transport.

``sandbox_node`` is production wiring around one fixture: the real
``CommandStream``, the real ``CommandActor``, the real egress envelope, and a
venue that emits the P0.3 event shapes instead of matching anything. These
tests assert the wiring, so that when ``tests/e2e`` is skipped for want of a
Redis the node half of GATE G1 is still covered.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from algobots.gateway.nodes import RedisCommandBus
from algobots.node.command_actor import DUPLICATE, SUBMITTED
from algobots.node.command_stream import stream_key
from algobots.node.event_egress import events_glob
from algobots.node.sandbox import ACCEPTED, DENIED, FILLED, sandbox_node, trader_id_for
from tests.fakes import FakeRedis

NODE = "nautilus-g1-test"
ACCOUNT = "g1-test"


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture
def node(redis):  # noqa: ANN001, ANN201
    built = sandbox_node(
        client=redis,
        account_id=ACCOUNT,
        node_name=NODE,
        nautilus_account_id="SIM-G1",
        venue="PAPER_G1",
    )
    built.stream.ensure_group()
    return built


def command(client_order_id: str, **overrides) -> dict:  # noqa: ANN003
    """What ``OrderIntent.command`` puts on ``algobots:cmd:<node>``."""
    return {
        "command": "submit_order",
        "client_order_id": client_order_id,
        "account_id": ACCOUNT,
        "symbol": "EUR/USD.SIM",
        "side": "buy",
        "qty": "100000",
        "order_type": "market",
        "time_in_force": "gtc",
        "reduce_only": False,
        "mode": "PAPER",
        **overrides,
    }


def published(redis: FakeRedis) -> list[dict]:
    """Every event this node published, in the order it published them."""
    import fnmatch

    out = []
    for key in redis.streams:
        if fnmatch.fnmatch(key, events_glob(trader_id_for(NODE))):
            out += [(entry_id, json.loads(f["payload"])) for entry_id, f in redis.entries(key)]
    return [payload for _entry_id, payload in sorted(out, key=lambda pair: pair[0])]


def test_a_command_on_the_stream_becomes_the_nautilus_event_sequence(redis, node):  # noqa: ANN001
    """One market order in, the engine's own lifecycle out."""
    RedisCommandBus(client=redis).publish(NODE, command("g1-wire-0001"))

    outcomes = node.stream.poll()

    assert [o.action for o in outcomes] == [SUBMITTED]
    assert [event["type"] for event in published(redis)] == [
        "OrderInitialized",
        "OrderSubmitted",
        "OrderAccepted",
        "OrderFilled",
        "PositionOpened",
    ]
    assert node.execution.statuses == {"g1-wire-0001": FILLED}


def test_the_idempotency_key_reaches_the_venue_verbatim(redis, node):  # noqa: ANN001
    """The line P1.3 is about, observed on the node's own event stream."""
    key = "g1-verbatim-0001"
    RedisCommandBus(client=redis).publish(NODE, command(key))
    node.stream.poll()

    ids = {event["client_order_id"] for event in published(redis) if "client_order_id" in event}
    assert ids == {key}


def test_redelivery_submits_once_and_publishes_one_fill(redis, node):  # noqa: ANN001
    """At-least-once delivery, absorbed. The entry is acked either way."""
    bus = RedisCommandBus(client=redis)
    key = "g1-redeliver-001"
    bus.publish(NODE, command(key))
    bus.publish(NODE, command(key))

    outcomes = node.stream.poll()

    assert [o.action for o in outcomes] == [SUBMITTED, DUPLICATE]
    assert [e["type"] for e in published(redis)].count("OrderFilled") == 1
    assert redis.pending_count(stream_key(NODE), node.stream.group) == 0


def test_an_unacked_entry_is_replayed_without_a_second_order(redis, node):  # noqa: ANN001
    """The restart path: ``drain_pending`` before anything new is read."""
    bus = RedisCommandBus(client=redis)
    key = "g1-restart-0001"
    bus.publish(NODE, command(key))
    # Delivered but never acked — a node that died mid-submission.
    redis.xreadgroup(node.stream.group, "node-1", {stream_key(NODE): ">"})
    node.execution.statuses[key] = FILLED  # the engine's reconciled cache

    recovered = node.stream.drain_pending()

    assert [o.action for o in recovered] == [DUPLICATE]
    assert published(redis) == []


def test_a_duplicate_that_reaches_the_venue_is_denied_rather_than_raised(redis, node):  # noqa: ANN001
    """The backstop Nautilus provides, as an event the gateway can fold.

    Raising here would leave the stream entry unacked and take the node down
    on a duplicate the actor exists to absorb.
    """
    key = "g1-denied-00001"
    node.execution.statuses[key] = FILLED

    from algobots.node.commands import SubmitOrder

    node.execution.submit(
        SubmitOrder(
            client_order_id=key,
            account_id=ACCOUNT,
            symbol="EUR/USD.SIM",
            side="buy",
            qty=Decimal("1"),
            order_type="market",
        )
    )

    assert [event["type"] for event in published(redis)] == ["OrderDenied"]
    assert node.execution.statuses[key] == DENIED


def test_a_working_order_stops_at_accepted_when_the_node_does_not_fill(redis):  # noqa: ANN001
    """``fill=False`` is how the gate gets an order to cancel."""
    node = sandbox_node(client=redis, account_id=ACCOUNT, node_name=NODE, fill=False)
    node.stream.ensure_group()
    key = "g1-working-0001"
    RedisCommandBus(client=redis).publish(NODE, command(key))

    node.stream.poll()

    assert node.execution.statuses == {key: ACCEPTED}
    assert [event["type"] for event in published(redis)] == [
        "OrderInitialized",
        "OrderSubmitted",
        "OrderAccepted",
    ]


def test_the_heartbeat_reports_the_nodes_reconciliation_state(redis, node):  # noqa: ANN001
    """Entry-frozen while reconciling (ALG-3258), read off the event stream."""
    node.heartbeat(reconciled=False, ts=1_700_000_000.0)

    beat = published(redis)[-1]
    assert beat["type"] == "AlgoBotsHeartbeat"
    assert beat["node"] == NODE
    assert beat["reconciled"] is False
    assert beat["ts"] == 1_700_000_000.0


def test_the_sandbox_node_never_writes_to_a_gateway_projection(redis, node):  # noqa: ANN001
    """Its own projection stays empty: the only fold that counts is the
    gateway's, reached through Redis. If this node could write to the store the
    gateway serves, GATE G1 would pass whenever the fixture worked.
    """
    RedisCommandBus(client=redis).publish(NODE, command("g1-isolated-001"))
    node.stream.poll()

    own = node.execution.fixture.projection
    assert own.orders(accounts=(ACCOUNT,), status=None, limit=100) == []
    assert own.head == 0
