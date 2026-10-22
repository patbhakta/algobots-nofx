"""The deployed gateway: :func:`~algobots.gateway.app.build_gateway` wired from the environment.

``build_gateway`` takes every collaborator as an argument so the contract suite
and GATE G1 can hand it fixtures. A container cannot, so this module is the one
place the real ones are chosen (ALG-3404):

- **projection** — :class:`~algobots.gateway.store.SqlProjection` on
  ``DATABASE_URL`` (the stack Postgres; migration 0011 owns the tables).
- **bus** — :class:`~algobots.gateway.nodes.RedisCommandBus` on ``REDIS_URL``.
- **registry** — ``ALGOBOTS_GATEWAY_NODES``, a JSON list of
  :class:`~algobots.gateway.nodes.Node` fields. Paper only: a node configured
  with any other mode is refused at boot, not at the first order.
- **sessions** — ``ALGOBOTS_GATEWAY_SESSIONS``, a JSON object of
  ``token -> {"principal": ..., "accounts": [...]}``. Unset means
  :class:`~algobots.gateway.auth.NoSessions`: every authenticated route is a
  ``401`` until the deploy supplies tokens. They live in the deploy's ``.env``,
  never in this repository (roadmap rule 3).
- **gate** — :class:`PaperLimitsGate`, the deploy's pre-trade gate.
- **ingest** — one :class:`~algobots.gateway.event_ingest.NodeEventIngest`
  thread folding every node's event streams into the projection.

Run with ``uvicorn algobots.gateway.serve:create_app --factory``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from fastapi import FastAPI

from algobots.gateway.admission import GateDecision, OrderIntent
from algobots.gateway.app import build_gateway
from algobots.gateway.auth import Caller, NoSessions, Sessions, StaticSessions
from algobots.gateway.event_ingest import NodeEventIngest
from algobots.gateway.nodes import PAPER, Node, NodeRegistry, RedisCommandBus
from algobots.gateway.store import SqlProjection
from algobots.node.command_stream import GROUP, stream_key

log = logging.getLogger("algobots.gateway")

#: Refusal codes of :class:`PaperLimitsGate`.
KILL_SWITCH = "kill_switch"
QTY_LIMIT = "qty_limit"


@dataclass(frozen=True)
class PaperLimitsGate:
    """Kill switch and a per-order quantity ceiling — the deploy's pre-trade gate.

    The ALG-3262 checks that need a balance (sleeve floor, daily loss,
    affordability) need the projection's account rows, which only exist once a
    node reports them; until then this is the gate, and it is not ``AllowAll``.
    """

    killed: bool = False
    max_qty: Decimal | None = None

    def pre_trade(self, intent: OrderIntent) -> GateDecision:
        if self.killed:
            return GateDecision(False, KILL_SWITCH, "trading is halted by the gateway kill switch")
        if self.max_qty is not None and intent.qty > self.max_qty:
            return GateDecision(
                False, QTY_LIMIT, f"qty {intent.qty} exceeds the per-order limit {self.max_qty}"
            )
        return GateDecision(True)


def registry_from(raw: str | None) -> NodeRegistry:
    """``ALGOBOTS_GATEWAY_NODES`` -> registry. Any non-paper node fails the boot."""
    registry = NodeRegistry()
    for spec in json.loads(raw) if raw else []:
        node = Node(**spec)
        if node.mode != PAPER:
            raise ValueError(f"node {node.node}: mode {node.mode!r} — the gateway is paper only")
        registry.add(node)
    return registry


def sessions_from(raw: str | None) -> Sessions:
    """``ALGOBOTS_GATEWAY_SESSIONS`` -> sessions; unset is fail-closed."""
    if not raw:
        return NoSessions()
    return StaticSessions(
        {
            token: Caller(spec["principal"], tuple(spec["accounts"]))
            for token, spec in json.loads(raw).items()
        }
    )


def gate_from(env: Mapping[str, str]) -> PaperLimitsGate:
    raw_max = env.get("ALGOBOTS_GATEWAY_MAX_QTY", "")
    return PaperLimitsGate(
        killed=env.get("ALGOBOTS_GATEWAY_KILL", "") in ("1", "true", "yes"),
        max_qty=Decimal(raw_max) if raw_max else None,
    )


def ensure_command_streams(client: Any, registry: NodeRegistry) -> list[str]:
    """Create each registered node's ``algobots:cmd:<node>`` stream and group.

    The same ``XGROUP CREATE ... MKSTREAM`` the node's ``CommandStream`` runs,
    so whichever side boots first, the other finds the group, and a command
    published before the node starts waits in the group rather than being read
    past at ``$``.
    """
    created = []
    for node in registry.accounts():
        key = stream_key(node.node)
        try:
            client.xgroup_create(key, GROUP, id="0", mkstream=True)
        except Exception as exc:  # redis.exceptions.ResponseError — BUSYGROUP is fine
            if "BUSYGROUP" not in str(exc):
                raise
        created.append(key)
    return created


def _ingest_forever(ingest: NodeEventIngest) -> None:
    """Run the ingest loop; if it dies, take the process with it.

    ``NodeEventIngest.run`` lets errors propagate so a lost Redis connection is
    not a projection that silently stopped advancing. In a container the honest
    version of that is exiting and letting the restart policy bring it back.
    """
    try:
        ingest.run()
    except Exception:
        log.exception("event ingest stopped; exiting so the container restarts")
    os._exit(1)


def create_app(env: Mapping[str, str] | None = None) -> FastAPI:
    import redis
    from sqlalchemy import create_engine

    env = os.environ if env is None else env
    registry = registry_from(env.get("ALGOBOTS_GATEWAY_NODES"))
    # Same driver normalisation as api.config: psycopg 3 is the installed driver.
    url = env["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    projection = SqlProjection(create_engine(url, pool_pre_ping=True))
    client = redis.Redis.from_url(env["REDIS_URL"])

    streams = ensure_command_streams(client, registry)
    log.info("gateway: %d node(s), command streams %s", len(streams), streams)

    app = build_gateway(
        registry=registry,
        gate=gate_from(env),
        projection=projection,
        bus=RedisCommandBus(client=client),
        sessions=sessions_from(env.get("ALGOBOTS_GATEWAY_SESSIONS")),
    )
    ingest = NodeEventIngest(client=client, registry=registry, projection=projection)

    def _start_ingest() -> None:
        threading.Thread(target=_ingest_forever, args=(ingest,), daemon=True).start()

    app.add_event_handler("startup", _start_ingest)
    return app


__all__ = [
    "KILL_SWITCH",
    "QTY_LIMIT",
    "PaperLimitsGate",
    "create_app",
    "ensure_command_streams",
    "gate_from",
    "registry_from",
    "sessions_from",
]
