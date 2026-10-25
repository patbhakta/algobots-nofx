"""ALG-3431: a RUNNING deployment's frozen decision reaches its own node via the gateway."""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from tests.deployments.test_momentum_intent import configured_deployment, rows
from tests.deployments.test_runtime import account

from algobots.api.deployments.runtime import launch_spec, node_identity
from algobots.gateway import deployment_nodes as DN
from algobots.gateway.app import build_gateway
from algobots.gateway.auth import NoSessions, StaticSessions
from algobots.gateway.nodes import InMemoryCommandBus, Node, NodeRegistry
from algobots.gateway.projection import OrderRow
from algobots.gateway.serve import PaperLimitsGate
from algobots.gateway.store import METADATA, SqlProjection
from algobots.node.deployment_dispatch import Dispatcher, read_feed

TOKEN = "dispatch-token-xyz"
NOW = 20001.0


def feed(tmp_path, book_ts=20000.0, market="KXBTC15M-TEST"):
    path = tmp_path / "observations.jsonl"
    lines = [json.dumps(r) for r in rows()]
    lines.append(
        json.dumps({"market": market, "ts": book_ts, "mkt_yes_bid": 0.40, "mkt_yes_ask": 0.45})
    )
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def gateway(registry):
    bus = InMemoryCommandBus()
    app = build_gateway(
        registry=registry,
        gate=PaperLimitsGate(max_qty=None),
        bus=bus,
        sessions=DN.DispatchSessions(NoSessions(), TOKEN, registry),
    )
    return TestClient(app), bus


def http_poster(client):
    def post(key, body):
        return client.post(
            "/v1/orders",
            json=body,
            headers={"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key},
        ).status_code

    return post


def test_node_identity_is_shared_by_supervisor_and_gateway():
    d = configured_deployment()
    spec = launch_spec(d, account(d))
    node = DN.deployment_node(d)
    assert (node.node, node.venue) == node_identity(d.id)
    assert spec.environment["ALGOBOTS_NODE"] == node.node
    assert spec.environment["ALGOBOTS_NODE_ACCOUNT"] == node.nautilus_account_id
    assert node.account_id == str(d.account_id)


def test_running_deployment_order_reaches_its_own_node_once(tmp_path):
    d = configured_deployment()
    registry = NodeRegistry()
    assert DN.sync(registry, [(d, account(d), None)]) == [node_identity(d.id)[0]]
    client, bus = gateway(registry)
    dispatch = Dispatcher(http_poster(client), feed(tmp_path), clock=lambda: NOW)
    children = {str(d.id): object()}

    # Node not yet heartbeating: 503 is retried, nothing published.
    assert len(dispatch([(d, account(d), None)], children)) == 1
    assert bus.published == [] and dispatch.done == {}

    registry.heartbeat(node_identity(d.id)[0])
    [key] = dispatch([(d, account(d), None)], children)
    assert dispatch.done == {key: 201}
    [(target, command)] = bus.published
    assert target == node_identity(d.id)[0]
    assert command["client_order_id"] == key and key.startswith("dp1-")

    # Same market again (or after a supervisor restart): no second command.
    assert dispatch([(d, account(d), None)], children) == []
    restarted = Dispatcher(http_poster(client), dispatch.feed_path, clock=lambda: NOW)
    restarted([(d, account(d), None)], children)
    assert restarted.done == {key: 200} and len(bus.published) == 1


def test_dead_or_unsupervised_deployment_is_not_dispatched(tmp_path):
    d = configured_deployment()
    calls = []
    dispatch = Dispatcher(lambda k, b: calls.append(k) or 201, feed(tmp_path), clock=lambda: NOW)
    assert dispatch([(d, account(d), None)], {}) == []
    assert calls == []


def test_stale_book_abstains(tmp_path):
    d = configured_deployment()
    calls = []
    dispatch = Dispatcher(lambda k, b: calls.append(k) or 201, feed(tmp_path), clock=lambda: 30000)
    assert dispatch([(d, account(d), None)], {str(d.id): object()}) == []


@pytest.mark.parametrize(
    "halt",
    [
        {"status": "stopped"},
        {"status": "paused"},
        {"breaker_state": "open"},
        "fleet",
    ],
)
def test_stop_or_breaker_halts_admission_at_the_gateway(tmp_path, halt):
    d = configured_deployment()
    registry = NodeRegistry()
    DN.sync(registry, [(d, account(d), None)])
    node = node_identity(d.id)[0]
    registry.heartbeat(node)
    fleet = None
    if halt == "fleet":
        fleet = SimpleNamespace(state="open", reason="fleet")
    else:
        for key, value in halt.items():
            setattr(d, key, value)
    DN.sync(registry, [(d, account(d), fleet)])
    assert node in registry.nodes and registry.nodes[node].halted
    client, bus = gateway(registry)
    # The supervisor is deliberately bypassed: the gateway refuses on its own.
    status = http_poster(client)(
        "dp1-" + "0" * 60,
        {
            "account_id": str(d.account_id),
            "symbol": "KXBTC15M/USD.X",
            "side": "buy",
            "qty": "1",
            "order_type": "limit",
            "limit_px": "0.45",
            "time_in_force": "ioc",
        },
    )
    assert status == 503 and bus.published == []


def test_stopped_deployment_is_never_registered_after_restart():
    d = configured_deployment()
    d.status = "stopped"
    registry = NodeRegistry()
    assert DN.sync(registry, [(d, account(d), None)]) == []
    assert registry.nodes == {}


def test_second_deployment_on_a_served_account_is_refused():
    d = configured_deployment()
    other = configured_deployment()
    other.account_id = d.account_id
    registry = NodeRegistry()
    DN.sync(registry, [(d, account(d), None), (other, account(other), None)])
    assert list(registry.nodes) == [node_identity(d.id)[0]]


def test_unreadable_lifecycle_halts_every_deployment_node():
    d = configured_deployment()
    registry = NodeRegistry()
    DN.sync(registry, [(d, account(d), None)])
    registry.add(Node("nautilus-paper", "paper", "demo", "SIM", "SIM-001"))
    stopped = SimpleNamespace(is_set=lambda: False)
    calls = []

    def read():
        raise RuntimeError("db down")

    def wait(_):
        calls.append(1)
        stopped.is_set = lambda: True

    stopped.wait = wait
    DN.sync_forever(registry, read, lambda added: None, stopped)
    assert registry.nodes[node_identity(d.id)[0]].halted
    assert not registry.nodes["nautilus-paper"].halted


def test_dispatcher_token_is_scoped_to_deployment_accounts():
    d = configured_deployment()
    registry = NodeRegistry()
    registry.add(Node("nautilus-paper", "paper", "demo", "SIM", "SIM-001"))
    DN.sync(registry, [(d, account(d), None)])
    base = StaticSessions({})
    sessions = DN.DispatchSessions(base, TOKEN, registry)
    assert sessions.caller(TOKEN).accounts == (str(d.account_id),)
    assert sessions.caller("wrong") is None
    assert DN.DispatchSessions(base, "", registry).caller("") is None


def test_read_feed_keeps_last_book_and_all_rows(tmp_path):
    history, book = read_feed(feed(tmp_path))
    assert len(history) == len(rows()) + 1
    assert book.market == "KXBTC15M-TEST" and str(book.ask) == "0.45"
    assert read_feed(str(tmp_path / "missing.jsonl")) == ([], None)


def test_live_tab_attributes_fills_by_deployment_node(tmp_path, monkeypatch):
    from algobots.api.deployments import service
    from algobots.api.routers import nofx

    engine = sa.create_engine(f"sqlite:///{tmp_path / 'p.db'}")
    METADATA.create_all(engine)
    projection = SqlProjection(engine)
    d = configured_deployment()
    d.frozen_spec["name"] = "owned momentum"
    node = node_identity(d.id)[0]
    for cid, owner in (("dp1-" + "a" * 60, node), ("demo-order-1", "nautilus-paper")):
        projection.put_order(
            OrderRow(
                client_order_id=cid,
                account_id=str(d.account_id),
                symbol="KXBTC15M/USD.X",
                side="buy",
                qty=Decimal("2"),
                order_type="limit",
                status="submitted",
                submitted_at="2026-10-25T21:00:00.000Z",
                updated_at="2026-10-25T21:00:00.000Z",
                node=owner,
            )
        )
    monkeypatch.setattr(service, "list_deployments", lambda db, user: [d])
    out, error = nofx._deployments_live(SimpleNamespace(get_bind=lambda: engine), object())
    assert error is None
    [row] = out
    assert row["node"] == node and row["strategy"] == "owned momentum"
    assert [o["client_order_id"] for o in row["orders"]] == ["dp1-" + "a" * 60]
