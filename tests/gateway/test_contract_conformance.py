"""P1.1: exercise the published gateway contract against a fixture node."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from jsonschema import Draft202012Validator, RefResolver
from starlette.websockets import WebSocketDisconnect

from algobots.gateway.admission import AllowAll, GateDecision
from algobots.gateway.app import (
    build_gateway,
    cancel_order,
    get_account,
    get_health,
    get_order,
    list_accounts,
    list_orders,
    list_positions,
    stream_events,
    submit_order,
)
from algobots.gateway.auth import Caller, StaticSessions
from algobots.gateway.errors import GatewayError
from algobots.gateway.fixture_node import fixture_stack

SPEC = yaml.safe_load(
    (Path(__file__).resolve().parents[2] / "contracts" / "gateway.openapi.yaml").read_text()
)
AUTH = {"Authorization": "Bearer fixture-session"}


def assert_schema(name: str, body: object) -> None:
    schema = SPEC["components"]["schemas"][name]
    validator = Draft202012Validator(schema, resolver=RefResolver.from_schema(SPEC))
    errors = sorted(validator.iter_errors(body), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


@pytest.fixture
def rig():
    registry, projection, bus, node = fixture_stack()
    node.heartbeat()
    node.account_state("1000.00", free="997.80", locked="2.20")
    app = build_gateway(
        registry=registry,
        projection=projection,
        bus=bus,
        gate=AllowAll(),
        sessions=StaticSessions({"fixture-session": Caller("member-1", ("laya",))}),
    )
    return app, node, bus, projection


@pytest.fixture
def anyio_backend():
    return "asyncio"


def request(app):  # noqa: ANN001, ANN201
    return SimpleNamespace(app=app, headers={"authorization": AUTH["Authorization"]})


def response_json(response) -> object:  # noqa: ANN001
    return json.loads(response.body)


def test_read_operations_match_contract(rig) -> None:
    app, _, _, _ = rig
    req = request(app)
    assert_schema("Health", get_health(req))

    accounts = list_accounts(req)
    assert_schema("Account", accounts["accounts"][0])
    assert_schema("Account", get_account(req, "laya"))

    assert list_positions(req, None)["positions"] == []
    assert list_orders(req, None, None, 100) == {"orders": []}


def test_submit_fixture_fill_get_list_and_events_match_contract(rig) -> None:
    app, node, _, projection = rig
    req = request(app)
    payload = {
        "account_id": "laya",
        "symbol": "EUR/USD.SIM",
        "side": "buy",
        "qty": "2",
        "order_type": "market",
    }
    created = submit_order(req, payload, "order-fixture-001")
    assert created.status_code == 201
    assert_schema("Order", response_json(created))
    assert len(node.bus.commands_for(node.node.node)) == 1

    replay = submit_order(req, payload, "order-fixture-001")
    assert replay.status_code == 200
    assert len(node.bus.commands_for(node.node.node)) == 1

    node.drain()
    fetched = get_order(req, "order-fixture-001")
    assert fetched["status"] == "filled"
    assert_schema("Order", fetched)

    listed = list_orders(req, "laya", "filled", 100)
    assert_schema("Order", listed["orders"][0])
    positions = list_positions(req, "laya")
    assert_schema("Position", positions["positions"][0])
    for event in projection.events_since(0, accounts=("laya",)):
        assert_schema("Event", event)


@pytest.mark.anyio
async def test_cancel_and_websocket_stream_match_contract(rig) -> None:
    app, node, _, projection = rig
    req = request(app)
    submit_order(
        req,
        {
            "account_id": "laya",
            "symbol": "EUR/USD.SIM",
            "side": "sell",
            "qty": "1",
            "order_type": "limit",
            "limit_px": "1.20",
        },
        "order-fixture-002",
    )
    node.drain(fill=False)
    cancel = cancel_order(req, "order-fixture-002", "cancel-fixture-02")
    assert cancel.status_code == 202
    assert_schema("Order", response_json(cancel))
    node.drain()
    assert get_order(req, "order-fixture-002")["status"] == "cancelled"

    since = projection.head - 1
    websocket = FixtureWebSocket(app, since)
    await stream_events(websocket)
    event = websocket.sent[0]
    assert_schema("Event", event)
    assert event["seq"] == projection.head


def test_admission_refusal_is_typed_and_never_published(rig) -> None:
    app, _, bus, projection = rig
    with pytest.raises(GatewayError) as raised:
        submit_order(
            request(app),
            {
            "account_id": "laya",
            "symbol": "EUR/USD.SIM",
            "side": "buy",
            "qty": 2,
            "order_type": "market",
            },
            "refused-fixture-1",
        )
    error = raised.value
    assert error.status == 422
    assert_schema("Error", error.body())
    assert bus.published == []
    assert projection.order("refused-fixture-1") is None


class DenyGate:
    def pre_trade(self, _intent):  # noqa: ANN001
        return GateDecision(False, "kill_switch", "paper trading is paused")


def test_pre_trade_denial_is_never_published() -> None:
    registry, projection, bus, node = fixture_stack()
    node.heartbeat()
    app = build_gateway(
        registry=registry,
        projection=projection,
        bus=bus,
        gate=DenyGate(),
        sessions=StaticSessions({"fixture-session": Caller("member-1", ("laya",))}),
    )
    with pytest.raises(GatewayError) as raised:
        submit_order(
            request(app),
            {
                "account_id": "laya",
                "symbol": "EUR/USD.SIM",
                "side": "buy",
                "qty": "2",
                "order_type": "market",
            },
            "denied-fixture-01",
        )
    assert raised.value.status == 403
    assert raised.value.body()["code"] == "kill_switch"
    assert bus.published == []
    assert projection.order("denied-fixture-01") is None


class FixtureWebSocket:
    """The ASGI WebSocket seam, stopped after the first contract frame."""

    def __init__(self, app, since: int) -> None:  # noqa: ANN001
        self.app = app
        self.headers = {"authorization": AUTH["Authorization"]}
        self.query_params = {"account": "laya", "since": str(since)}
        self.sent: list[dict] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, body: dict) -> None:
        self.sent.append(body)
        raise WebSocketDisconnect()

    async def close(self, code: int, reason: str) -> None:
        raise AssertionError(f"unexpected WebSocket close {code}: {reason}")
