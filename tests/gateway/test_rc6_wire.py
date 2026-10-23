"""ALG-3405: the gateway folds what a Nautilus 2.0.0rc6 node actually writes.

``fixtures/rc6_event_streams.json`` is a capture off ``.243``'s Redis: one
rc6 ``LiveNode`` (:mod:`algobots.node.paper_node`) taking one market order
from ``algobots:cmd:proto-3405`` and filling it on the sandbox venue. Unlike
the 1.231 capture the P1 code was written against, rc6 wraps order and
position events in their enum variant, leaves ``type`` off ``AccountState``
and position payloads, stamps every ``ts_*`` in integer nanoseconds, and
publishes each order event a second time on a per-type topic.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from tests.fakes import FakeRedis

from algobots.gateway import node_events as NE
from algobots.gateway.event_ingest import NodeEventIngest, decode
from algobots.gateway.fixture_node import fixture_stack

CAPTURE = json.loads((Path(__file__).parent / "fixtures" / "rc6_event_streams.json").read_text())
ENTRIES = CAPTURE["entries"]
CLIENT_ORDER_ID = "proto-3405-0001"


def _entry(topic_prefix: str) -> dict:
    return next(e for e in ENTRIES if e["fields"]["topic"].startswith(topic_prefix))


@pytest.fixture
def stack():  # noqa: ANN201
    registry, projection, _bus, _node = fixture_stack(
        node_name="proto-3405", account_id="laya", nautilus_account_id="SIM-001"
    )
    projection.put_order(
        NE.admitted_order(
            client_order_id=CLIENT_ORDER_ID,
            account_id="laya",
            node="proto-3405",
            symbol="EUR/USD.SIM",
            side="buy",
            qty=Decimal("1000"),
            order_type="market",
            now=1792650736.0,
        )
    )
    redis = FakeRedis()
    for e in ENTRIES:
        redis.xadd(e["key"], e["fields"])
    ingest = NodeEventIngest(
        client=redis, registry=registry, projection=projection, trader_id="PROTO-3405"
    )
    return registry, projection, ingest


def test_an_rc6_fill_is_unwrapped_and_its_nanoseconds_become_seconds():
    fill = next(
        decode(e["fields"])
        for e in ENTRIES
        if e["fields"]["topic"].startswith("events.order.") and '"Filled"' in e["fields"]["payload"]
    )
    assert fill["type"] == "OrderFilled"
    assert fill["client_order_id"] == CLIENT_ORDER_ID
    assert 1.7e9 < fill["ts_event"] < 1.9e9


def test_account_state_and_positions_take_their_type_from_the_envelope():
    account = decode(_entry("events.account.")["fields"])
    position = decode(_entry("events.position.")["fields"])
    assert account["type"] == "AccountState"
    assert position["type"] == "PositionOpened"


def test_the_per_type_copies_and_portfolio_snapshots_are_not_folded():
    for prefix in ("events.order_submitted.", "events.order_filled.", "events.portfolio."):
        assert decode(_entry(prefix)["fields"]) is None, prefix


def test_a_1231_payload_passes_through_normalize_unchanged():
    payload = {"type": "OrderFilled", "client_order_id": "x", "ts_event": "2026-10-13T00:00:00Z"}
    assert NE.normalize(payload, "OrderEventAny") == payload


def test_the_captured_rc6_run_folds_into_one_filled_order(stack):  # noqa: ANN001
    registry, projection, ingest = stack
    ingest.poll()
    ingest.poll()  # a second pass replays nothing

    order = projection.order(CLIENT_ORDER_ID)
    assert order is not None
    assert order.status == "filled"
    assert order.filled_qty == Decimal("1000")
    assert order.avg_px == Decimal("1.10003")

    (position,) = projection.positions(accounts=("laya",))
    assert position.qty == Decimal("1000") and position.side == "buy"

    (usd,) = projection.balances("laya")
    assert usd["currency"] == "USD" and usd["total"] == "100000"

    node = registry.nodes["proto-3405"]
    assert node.reconciled and node.last_heartbeat is not None

    fills = [e for e in projection.events_since(0, accounts=("laya",)) if e["type"] == "fill"]
    assert len(fills) == 1
