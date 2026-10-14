"""The two processes GATE G1 measures across, assembled over real services.

The gateway and the node are separate threads here rather than separate
containers, and that is the one concession this harness makes. It is a safe
one, because they share no object: the node has its own registry and its own
(unread) projection, and everything that passes between them passes through
Redis. Replacing the threads with containers would change where the code runs,
not which code runs or what it talks over.

Three loops, which are the three the deploy runs:

1. **uvicorn** serving ``algobots.gateway.app`` — the HTTP surface NoFX calls.
2. **``CommandStream``** on the node, reading ``algobots:cmd:<node>``.
3. **``NodeEventIngest``** in the gateway, reading the node's event streams.

``scripts/verify_g1.py`` builds the same stack, so the repository script and
the CI job measure the same thing.
"""

from __future__ import annotations

import socket
import threading
import time
from contextlib import closing, contextmanager
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import httpx
import uvicorn

from algobots.gateway.admission import AllowAll
from algobots.gateway.app import PREFIX, build_gateway
from algobots.gateway.auth import Caller, StaticSessions
from algobots.gateway.event_ingest import NodeEventIngest
from algobots.gateway.nodes import Node, NodeRegistry, RedisCommandBus
from algobots.gateway.store import SqlProjection
from algobots.node.sandbox import SandboxNode, sandbox_node, trader_id_for

#: The session token the harness mints. Not a credential: ``StaticSessions``
#: holds whatever the builder passes, so nothing secret is defined in the repo
#: (roadmap rule 3).
TOKEN = "g1-session"  # noqa: S105 — a test fixture's own token, not a secret

#: The instrument P0.3 captured its events on.
SYMBOL = "EUR/USD.SIM"

#: What a market fill prints at in the sandbox. Supplied, never computed — the
#: gate asserts the gateway reports *this* number, which is only meaningful
#: because nothing on the path is allowed to invent one.
FILL_PX = Decimal("1.10005")

#: How long to wait for the gateway's first ``/health``.
BOOT_TIMEOUT_S = 15.0


def free_port() -> int:
    with closing(socket.socket()) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class G1Stack:
    """Handles on the running stack, and the client leg NoFX would use."""

    base_url: str
    account_id: str
    node_name: str
    registry: NodeRegistry
    projection: SqlProjection
    ingest: NodeEventIngest
    node: SandboxNode
    client: httpx.Client

    # --- the client leg -------------------------------------------------------
    #
    # These four are `clients/gateway/client.gen.go`'s SubmitOrder, GetOrder,
    # ListAccounts and ListPositions: the same paths, the same headers, the
    # same bearer. NoFX's `nautilus` exchange (ALG-3372) calls the generated
    # client; the generated client makes exactly these requests.

    def submit_order(self, key: str, body: dict[str, Any]) -> httpx.Response:
        return self.client.post(
            f"{PREFIX}/orders", json=body, headers={"Idempotency-Key": key}
        )

    def get_order(self, client_order_id: str) -> httpx.Response:
        return self.client.get(f"{PREFIX}/orders/{client_order_id}")

    def list_accounts(self) -> httpx.Response:
        return self.client.get(f"{PREFIX}/accounts")

    def list_positions(self) -> httpx.Response:
        return self.client.get(f"{PREFIX}/positions")

    def health(self) -> httpx.Response:
        return self.client.get(f"{PREFIX}/health")

    def events_url(self, *, since: int | None = None) -> str:
        url = self.base_url.replace("http://", "ws://") + f"{PREFIX}/events"
        return url if since is None else f"{url}?since={since}"

    # --- waiting --------------------------------------------------------------

    def await_order(self, client_order_id: str, status: str, *, timeout: float) -> dict[str, Any]:
        """Poll ``GET /orders/{id}`` until it reports ``status``.

        Polling rather than reading the websocket, because this is the weaker
        of the two paths: ``/events`` pushes, so a gate that only watched it
        could pass while the read a page refresh performs was still stale.
        """
        deadline = time.monotonic() + timeout
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            response = self.get_order(client_order_id)
            if response.status_code == 200:
                last = response.json()
                if last.get("status") == status:
                    return last
            time.sleep(0.005)
        raise AssertionError(
            f"{client_order_id} never reached {status!r} within {timeout}s; last={last}"
        )

    def await_positions(self, count: int, *, timeout: float) -> list[dict[str, Any]]:
        """Poll ``GET /positions`` until ``count`` of them are open.

        A separate wait from :meth:`await_order`, because the position is a
        separate Redis stream: Nautilus publishes ``events.position.*`` and
        ``events.order.*`` independently, so an order can read ``filled`` one
        ingest poll before the position it opened appears. Asserting both at
        once would be asserting an ordering across streams that nothing
        guarantees — and that the contract does not promise either, which is
        why ``/positions`` carries its own ``as_of``.
        """
        deadline = time.monotonic() + timeout
        last: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            response = self.list_positions()
            if response.status_code == 200:
                last = response.json()["positions"]
                if len(last) >= count:
                    return last
            time.sleep(0.005)
        raise AssertionError(f"expected {count} open positions within {timeout}s; got {last}")

    def await_fit(self, *, timeout: float = 10.0) -> dict[str, Any]:
        """Beat until the gateway has read a heartbeat off the event stream.

        The node's liveness reaches the gateway the same way its fills do, so
        this also proves the ingest loop is running before anything is measured
        — a gate that submitted into an unfit node would fail with a 503 and
        say nothing about latency.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.node.heartbeat()
            body = self.health().json()
            if body["status"] == "ok" and all(n["reachable"] for n in body["nodes"]):
                return body
            time.sleep(0.05)
        raise AssertionError(f"node never became fit: {self.health().json()}")


@contextmanager
def g1_stack(*, engine: Any, redis_client: Any, run_id: str, fill: bool = True):  # noqa: ANN201
    """Start the gateway, the node and the ingest loop; stop them after."""
    node_name = f"nautilus-g1-{run_id}"
    account_id = f"g1-{run_id}"
    nautilus_account_id = f"SIM-{run_id.upper()}"

    registry = NodeRegistry()
    registry.add(
        Node(
            node=node_name,
            account_id=account_id,
            display_name="G1 paper",
            venue="PAPER_G1",
            nautilus_account_id=nautilus_account_id,
        )
    )
    projection = SqlProjection(engine)
    app = build_gateway(
        registry=registry,
        gate=AllowAll(),
        projection=projection,
        bus=RedisCommandBus(client=redis_client),
        sessions=StaticSessions({TOKEN: Caller("g1-member", (account_id,))}),
    )

    ingest = NodeEventIngest(
        client=redis_client,
        registry=registry,
        projection=projection,
        trader_id=trader_id_for(node_name),
        block_ms=25,
    )
    node = sandbox_node(
        client=redis_client,
        account_id=account_id,
        node_name=node_name,
        venue="PAPER_G1",
        nautilus_account_id=nautilus_account_id,
        display_name="G1 paper",
        fill_px=FILL_PX,
        fill=fill,
        # Short, so the loop notices the stop flag promptly. The deploy's
        # 5s block is the right default there and the wrong one in a test.
        block_ms=200,
    )
    # Before anything is published: the group is created at id 0, so a command
    # written while the node was still starting is read rather than skipped.
    node.stream.ensure_group()

    port = free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    # Not the main thread, so uvicorn may not install signal handlers.
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    stop = threading.Event()
    threads = [
        threading.Thread(target=server.run, name="g1-gateway", daemon=True),
        threading.Thread(target=lambda: node.run(until=stop.is_set), name="g1-node", daemon=True),
        threading.Thread(
            target=lambda: ingest.run(until=stop.is_set), name="g1-ingest", daemon=True
        ),
    ]
    for thread in threads:
        thread.start()

    base_url = f"http://127.0.0.1:{port}"
    client = httpx.Client(
        base_url=base_url, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10.0
    )
    try:
        _await_boot(client)
        yield G1Stack(
            base_url=base_url,
            account_id=account_id,
            node_name=node_name,
            registry=registry,
            projection=projection,
            ingest=ingest,
            node=node,
            client=client,
        )
    finally:
        stop.set()
        server.should_exit = True
        client.close()
        for thread in threads:
            thread.join(timeout=10.0)


def _await_boot(client: httpx.Client) -> None:
    deadline = time.monotonic() + BOOT_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            if client.get(f"{PREFIX}/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.05)
    raise AssertionError("the gateway never answered /v1/health")


__all__ = ["BOOT_TIMEOUT_S", "FILL_PX", "SYMBOL", "TOKEN", "G1Stack", "free_port", "g1_stack"]
