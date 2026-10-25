"""The gateway's HTTP surface — every operation in the contract, and no others.

``contracts/gateway.openapi.yaml`` is the definition (roadmap rule 2); this
module is its implementation. ``tests/gateway/test_contract_conformance.py``
drives all nine operations against a fixture node and validates every response
body against that file, so a route that drifts from the contract fails CI
rather than NoFX.

The one deliberate difference from the bridge it replaces: there is no route
here that executes anything. ``POST /orders`` admits and publishes a command;
the node fills. Everything the gateway reports back is a fold of what the node
then said (``projection``).

Since P1.2 that fold lives in Postgres
(:class:`~algobots.gateway.store.SqlProjection`), so no route here reads a
node's memory and a restarted gateway answers ``/orders`` and ``/positions``
with the same rows. Every route is written against the
:class:`~algobots.gateway.projection.Projection` protocol rather than a store,
which is why the P1.1 fixture suite and the P1.2 restart proof exercise the
same request code.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, Body, FastAPI, Header, Query, Request, WebSocket
from fastapi.responses import JSONResponse
from starlette.websockets import WebSocketDisconnect

from algobots.gateway.admission import PreTradeGate, admit, require_idempotency_key
from algobots.gateway.auth import (
    Caller,
    NoSessions,
    Sessions,
    require_caller,
    resolve_account,
    scope_accounts,
)
from algobots.gateway.errors import (
    ORDER_TERMINAL,
    UNKNOWN_ORDER,
    GatewayError,
    gateway_error_handler,
)
from algobots.gateway.node_events import account_contract
from algobots.gateway.nodes import (
    NAUTILUS_PIN,
    CommandBus,
    InMemoryCommandBus,
    NodeRegistry,
)
from algobots.gateway.projection import InMemoryProjection, OrderRow, Projection, iso

#: The contract's server URL ends in ``/v1``; paths in it are relative to that.
PREFIX = "/v1"

#: How often the ``/events`` tail re-reads the projection.
#:
#: Still a poll after P1.2, deliberately. ``LISTEN``/``NOTIFY`` would tie the
#: stream to PostgreSQL, and the thing the contract actually promises is the
#: cursor: every frame a client missed is addressable by ``seq``, so a reader
#: that is late by one poll interval loses nothing, it only learns late. The
#: notification would be an optimisation on top of the same query, and it would
#: cost CI the ability to run this stream at all.
EVENT_POLL_S = 0.01

GATEWAY_VERSION = "1.0.0-phase1"


@dataclass
class Gateway:
    """Everything a request needs, assembled once by :func:`build_gateway`."""

    registry: NodeRegistry
    projection: Projection
    bus: CommandBus
    gate: PreTradeGate
    sessions: Sessions = field(default_factory=NoSessions)
    version: str = GATEWAY_VERSION
    #: Cancel keys already acted on: cancelling twice cancels once.
    cancels: dict[str, str] = field(default_factory=dict)


def _gw(request: Request | WebSocket) -> Gateway:
    return request.app.state.gateway


def _caller(request: Request | WebSocket, authorization: str | None = None) -> Caller:
    gw = _gw(request)
    header = authorization if authorization is not None else request.headers.get("authorization")
    return require_caller(gw.sessions, header)


def _order_in_scope(gw: Gateway, client_order_id: str, caller: Caller) -> OrderRow:
    order = gw.projection.order(client_order_id)
    if order is None:
        raise GatewayError(404, UNKNOWN_ORDER, f"no order {client_order_id!r}")
    # Resolving the account is how an order belonging to another member becomes
    # a 403 rather than a leak.
    resolve_account(order.account_id, caller=caller, registry=gw.registry)
    return order


router = APIRouter()


@router.get("/health", tags=["system"])
def get_health(request: Request) -> dict[str, Any]:
    """Liveness, the Nautilus pin, node reachability, and the projection.

    Unauthenticated on purpose: it is the stack's liveness probe, and it names
    no account balance, order or member — only node ids, reachability and the
    event cursor.
    """
    gw = _gw(request)
    now = time.time()
    nodes = []
    live = []
    for node in gw.registry.accounts():
        reachable, _ = node.fit(now)
        if not node.halted:
            live.append(reachable)
        nodes.append(
            {
                "node": node.node,
                "account": node.account_id,
                "reachable": reachable,
                "last_heartbeat": iso(node.last_heartbeat) if node.last_heartbeat else None,
            }
        )
    # P1.2: the reads are served from Postgres, so a healthy fleet over an
    # unreachable projection is still degraded — the gateway could answer
    # neither /orders nor /positions.
    projection = gw.projection.health()
    # A halted deployment node is intent, not an outage.
    healthy = bool(live) and all(live) and projection["reachable"]
    return {
        "status": "ok" if healthy else "degraded",
        "version": gw.version,
        # Roadmap rule 5: an upgrade is its own sprint, so this is a pin, not
        # a lookup of whatever happens to be installed.
        "nautilus_version": NAUTILUS_PIN,
        "nodes": nodes,
        "projection": projection,
    }


@router.get("/accounts", tags=["accounts"])
def list_accounts(request: Request) -> dict[str, Any]:
    """The caller's granted accounts, oldest first. Never another member's."""
    gw = _gw(request)
    caller = _caller(request)
    return {
        "accounts": [
            account_contract(node, gw.projection.balances(node.account_id))
            for node in gw.registry.accounts()
            if node.account_id in caller.accounts
        ]
    }


@router.get("/accounts/{accountId}", tags=["accounts"])
def get_account(request: Request, accountId: str) -> dict[str, Any]:  # noqa: N803 — contract name
    """One account, with the balance its node last reported."""
    gw = _gw(request)
    caller = _caller(request)
    account_id = resolve_account(accountId, caller=caller, registry=gw.registry)
    node = gw.registry.by_account(account_id)
    assert node is not None
    return account_contract(node, gw.projection.balances(account_id))


@router.get("/positions", tags=["positions"])
def list_positions(request: Request, account: str | None = Query(default=None)) -> dict[str, Any]:
    """Open positions, as folded from the node event stream."""
    gw = _gw(request)
    caller = _caller(request)
    accounts = scope_accounts(account, caller=caller, registry=gw.registry)
    return {
        "positions": [p.contract() for p in gw.projection.positions(accounts=accounts)],
        "as_of": gw.projection.as_of,
    }


@router.get("/orders", tags=["orders"])
def list_orders(
    request: Request,
    account: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Orders and their fills, newest first."""
    gw = _gw(request)
    caller = _caller(request)
    accounts = scope_accounts(account, caller=caller, registry=gw.registry)
    rows = gw.projection.orders(accounts=accounts, status=status, limit=limit)
    return {"orders": [r.contract() for r in rows]}


@router.post("/orders", tags=["orders"])
def submit_order(
    request: Request,
    body: Any = Body(default=None),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Admit an order intent and queue it for the account's node.

    The body is taken raw rather than through a request model so that the
    admission order in ``admission.admit`` is the real order: a framework that
    validated the shape first would answer ``422`` to a caller who should have
    been told ``403``, and the refusal order is the thing under test.
    """
    gw = _gw(request)
    caller = _caller(request)
    admission, intent = admit(
        body,
        caller=caller,
        idempotency_key=idempotency_key,
        registry=gw.registry,
        projection=gw.projection,
        gate=gw.gate,
    )
    if admission.replay:
        return JSONResponse(status_code=200, content=admission.order.contract())
    assert intent is not None
    gw.bus.publish(intent.node, intent.command(now=time.time()))
    return JSONResponse(status_code=201, content=admission.order.contract())


@router.get("/orders/{clientOrderId}", tags=["orders"])
def get_order(request: Request, clientOrderId: str) -> dict[str, Any]:  # noqa: N803
    """One order with its lifecycle and fills."""
    gw = _gw(request)
    caller = _caller(request)
    return _order_in_scope(gw, clientOrderId, caller).contract()


@router.delete("/orders/{clientOrderId}", tags=["orders"])
def cancel_order(
    request: Request,
    clientOrderId: str,  # noqa: N803
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """Request cancellation. Also a command, so cancelling twice cancels once.

    The order comes back unchanged: the node confirms the cancellation on
    ``/events``, and the gateway does not pre-empt it by marking an order
    cancelled that the venue may still fill.
    """
    gw = _gw(request)
    caller = _caller(request)
    key = require_idempotency_key(idempotency_key)
    order = _order_in_scope(gw, clientOrderId, caller)
    if order.terminal:
        raise GatewayError(
            409, ORDER_TERMINAL, f"order {clientOrderId} is already {order.status}"
        )
    if gw.cancels.get(key) != clientOrderId:
        gw.cancels[key] = clientOrderId
        gw.registry.require_fit(order.account_id)
        gw.bus.publish(
            order.node,
            {
                "command": "cancel_order",
                "client_order_id": clientOrderId,
                "account_id": order.account_id,
                "idempotency_key": key,
                "requested_ts": time.time(),
            },
        )
    return JSONResponse(status_code=202, content=order.contract())


@router.websocket("/events")
async def stream_events(websocket: WebSocket) -> None:
    """Tail of the same projection ``/orders`` and ``/positions`` read.

    ``since`` resumes after a ``seq``; omitting it starts from now. Delivery is
    at-least-once by design — a node restart can replay a fill — so consumers
    dedupe on ``(client_order_id, seq)``.
    """
    gw = _gw(websocket)
    try:
        caller = _caller(websocket)
        accounts = scope_accounts(
            websocket.query_params.get("account"), caller=caller, registry=gw.registry
        )
    except GatewayError as exc:
        # The upgrade never happens: 1008 (policy violation) carries the code
        # so a client can tell "not logged in" from "not your account".
        await websocket.close(code=1008, reason=exc.code)
        return

    raw_since = websocket.query_params.get("since")
    cursor = int(raw_since) if raw_since not in (None, "") else gw.projection.head
    await websocket.accept()
    try:
        while True:
            for event in gw.projection.events_since(cursor, accounts=accounts):
                await websocket.send_json(event)
                cursor = event["seq"]
            await asyncio.sleep(EVENT_POLL_S)
    except WebSocketDisconnect:
        return


def build_gateway(
    *,
    registry: NodeRegistry,
    gate: PreTradeGate,
    projection: Projection | None = None,
    bus: CommandBus | None = None,
    sessions: Sessions | None = None,
    version: str = GATEWAY_VERSION,
) -> FastAPI:
    """Assemble the gateway.

    ``gate`` and ``registry`` are required: there is no deployment in which an
    open pre-trade gate or an implicit node is the right default. ``sessions``
    defaults to :class:`~algobots.gateway.auth.NoSessions`, so an
    unconfigured gateway answers ``401`` instead of inventing a principal.
    """
    app = FastAPI(
        title="AlgoBots Gateway",
        version=version,
        description="ROADMAP-v3 Phase 1 gateway — contracts/gateway.openapi.yaml is the API.",
    )
    app.state.gateway = Gateway(
        registry=registry,
        projection=projection if projection is not None else InMemoryProjection(),
        bus=bus if bus is not None else InMemoryCommandBus(),
        gate=gate,
        sessions=sessions if sessions is not None else NoSessions(),
        version=version,
    )
    app.add_exception_handler(GatewayError, gateway_error_handler)
    app.include_router(router, prefix=PREFIX)
    return app


__all__ = ["EVENT_POLL_S", "GATEWAY_VERSION", "PREFIX", "Gateway", "build_gateway", "router"]
