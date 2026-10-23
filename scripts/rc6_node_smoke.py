"""DEMO hop 3 smoke (ALG-3405): a gateway ``POST /v1/orders`` fills on the rc6 node.

Runs the real gateway app (``build_gateway`` + ``RedisCommandBus`` +
``NodeEventIngest``) in this process against the stack's Redis, and lets the
``nautilus-node`` container — Nautilus 2.0.0rc6, sandbox venue — do the rest:

    POST /v1/orders -> algobots:cmd:<node> -> CommandActor -> Strategy.submit_order
    -> SandboxExecutionClient fill -> trader-*:algobots:events.* -> GET /v1/orders/{id}

Only the projection is in memory; the gateway service itself is ALG-3404's to
deploy. Paper only: the node refuses anything but ``mode=PAPER``.

    REDIS_URL=redis://redis:6379/0 python scripts/rc6_node_smoke.py

Prints one JSON document (the evidence) and exits 0 only on a fill.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
import uuid

import httpx
import redis
import uvicorn

from algobots.gateway.admission import AllowAll
from algobots.gateway.app import PREFIX, build_gateway
from algobots.gateway.auth import Caller, StaticSessions
from algobots.gateway.event_ingest import NodeEventIngest
from algobots.gateway.nodes import Node, NodeRegistry, RedisCommandBus
from algobots.gateway.projection import InMemoryProjection
from algobots.node.sandbox import trader_id_for

NODE = os.environ.get("ALGOBOTS_NODE", "nautilus-paper")
NAUTILUS_ACCOUNT = os.environ.get("ALGOBOTS_NODE_ACCOUNT", "SIM-001")
SYMBOL = os.environ.get("ALGOBOTS_NODE_SYMBOL", "EUR/USD.SIM")
ACCOUNT = "paper"
QTY = "1000"
PORT = int(os.environ.get("SMOKE_PORT", "18405"))
PATIENCE_S = 20.0


def main() -> int:
    client = redis.Redis.from_url(os.environ.get("REDIS_URL", "redis://redis:6379/0"))
    token = secrets.token_urlsafe(16)
    registry = NodeRegistry()
    registry.add(
        Node(
            node=NODE,
            account_id=ACCOUNT,
            display_name="rc6 paper",
            venue="SIM",
            nautilus_account_id=NAUTILUS_ACCOUNT,
        )
    )
    projection = InMemoryProjection()
    app = build_gateway(
        registry=registry,
        gate=AllowAll(),
        projection=projection,
        bus=RedisCommandBus(client=client),
        sessions=StaticSessions({token: Caller("rc6-smoke", (ACCOUNT,))}),
    )
    ingest = NodeEventIngest(
        client=client, registry=registry, projection=projection, trader_id=trader_id_for(NODE)
    )
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    stop = threading.Event()
    for target in (server.run, lambda: ingest.run(until=stop.is_set)):
        threading.Thread(target=target, daemon=True).start()

    http = httpx.Client(
        base_url=f"http://127.0.0.1:{PORT}{PREFIX}",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    evidence: dict = {"node": NODE, "trader_id": trader_id_for(NODE), "symbol": SYMBOL}
    try:
        deadline = time.monotonic() + PATIENCE_S
        health: dict = {}
        while time.monotonic() < deadline:
            try:
                health = http.get("/health").json()
            except httpx.HTTPError:
                health = {}
            if health.get("status") == "ok":
                break
            time.sleep(0.2)
        evidence["health"] = health
        if health.get("status") != "ok":
            evidence["result"] = "node never became fit (no heartbeat on the event stream)"
            return 1

        key = f"rc6-smoke-{uuid.uuid4().hex[:12]}"
        body = {
            "account_id": ACCOUNT,
            "symbol": SYMBOL,
            "side": "buy",
            "qty": QTY,
            "order_type": "market",
            "time_in_force": "gtc",
        }
        started = time.monotonic()
        submitted = http.post("/orders", json=body, headers={"Idempotency-Key": key})
        evidence["post_orders"] = {"status_code": submitted.status_code, "body": submitted.json()}
        order: dict = {}
        while time.monotonic() - started < PATIENCE_S:
            order = http.get(f"/orders/{key}").json()
            if order.get("status") == "filled":
                break
            time.sleep(0.05)
        evidence["latency_s"] = round(time.monotonic() - started, 3)
        evidence["order"] = order
        evidence["positions"] = http.get("/positions").json()
        evidence["accounts"] = http.get("/accounts").json()
        ok = order.get("status") == "filled"
        evidence["result"] = "filled" if ok else "no fill"
        return 0 if ok else 1
    finally:
        stop.set()
        server.should_exit = True
        print(json.dumps(evidence, indent=2, default=str))


if __name__ == "__main__":
    sys.exit(main())
