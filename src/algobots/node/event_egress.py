"""The node's half of the event path: Nautilus events onto Redis streams.

P1.2 gave the gateway a durable fold of what a node said. P1.3 gave the node a
reader for what the gateway admitted. Neither sprint wrote the leg between
them — ``node_events.ingest`` was only ever called in-process — so until P1.5
there was no path by which a fill reached NoFX at all. This module and
:mod:`algobots.gateway.event_ingest` are that leg.

The wire shape is not invented here. It is the one P0.3 captured off a real
``nautilus_trader`` node configured with
:func:`~algobots.engine.redis_message_bus.redis_message_bus_config`
(``artifacts/ALG-3350/p03-redis-xread-evidence.md``): one Redis stream per
topic, keyed ``trader-{trader_id}:algobots:{topic}``, each entry carrying the
event as JSON in a ``payload`` field.

That is why this module publishes rather than transforms. In production the
publisher **is** Nautilus' own message bus — nothing here runs — and the
gateway reads the streams the engine wrote. What this module exists for is the
two cases Nautilus does not cover:

1. **The heartbeat.** Nautilus has no cross-engine liveness event, and the
   gateway's fitness check (``Node.fit``) needs one. The node emits
   ``AlgoBotsHeartbeat`` onto the same streams so there is one event path, not
   two, and so a node that has stopped publishing events is also a node that
   has stopped looking fit.
2. **The sandbox node** (:mod:`algobots.node.sandbox`), which drives GATE G1 in
   CI where the engine is absent.

Writing both through the same envelope is the point: if this envelope were
wrong, the sandbox would pass CI and the real node would not be read at all.
``tests/phase0/test_redis_egress_integration.py`` pins the key format against
the live capture, and ``tests/e2e`` reads these streams with the same consumer
the deploy runs.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

#: ``MessageBusConfig.streams_prefix``. Defined here rather than in
#: :mod:`algobots.engine.redis_message_bus` because that module imports
#: ``nautilus_trader`` at module scope and the gateway — which has to build the
#: same key to read it — does not have the dependency.
STREAMS_PREFIX = "algobots"

#: ``events.*`` is every order, position, account and system event. The glob
#: the gateway scans with is derived from this, so a topic the node starts
#: publishing is picked up without a gateway change.
EVENTS = "events"

#: Nautilus' own encoding marker. ``timestamps_as_iso8601=True`` and
#: ``encoding="json"`` are what the P0.3 config sets, and the reader refuses
#: anything else rather than guessing at msgpack bytes.
JSON_ENCODING = "Json"

#: AlgoBots' liveness beat. Not a Nautilus topic — see the module docstring.
HEARTBEAT_TOPIC = f"{EVENTS}.heartbeat"

#: Where each event type is published. Nautilus routes by the emitting
#: component (strategy id for orders and positions, account id for account
#: state), which is why the topic needs more than the event name to build.
ORDER_EVENTS = f"{EVENTS}.order"
POSITION_EVENTS = f"{EVENTS}.position"
ACCOUNT_EVENTS = f"{EVENTS}.account"


def stream_key(trader_id: str, topic: str) -> str:
    """``trader-ALGOBOTS-001:algobots:events.order.Strategy-000``.

    The trader prefix comes *before* ``streams_prefix`` — an ``algobots*``
    glob does not match these keys, which is the detail P0.3 recorded after
    scanning for the wrong pattern first.
    """
    return f"trader-{trader_id}:{STREAMS_PREFIX}:{topic}"


def events_glob(trader_id: str = "*") -> str:
    """Every event stream for a trader (or for every trader)."""
    return f"trader-{trader_id}:{STREAMS_PREFIX}:{EVENTS}.*"


def topic_for(payload: dict[str, Any]) -> str:
    """The topic Nautilus would publish this event on.

    Order and position events are routed by ``strategy_id`` and account state
    by ``account_id``, exactly as the capture shows. An event carrying neither
    still gets a topic under ``events.*`` so it is readable rather than lost —
    the gateway ignores what it does not recognise (``node_events.ingest``), so
    an unroutable event becomes a no-op and not a dropped fill.
    """
    kind = str(payload.get("type") or "")
    if kind == "AlgoBotsHeartbeat":
        return f"{HEARTBEAT_TOPIC}.{payload.get('node') or 'unknown'}"
    if kind == "AccountState":
        return f"{ACCOUNT_EVENTS}.{payload.get('account_id') or 'unknown'}"
    component = str(payload.get("strategy_id") or payload.get("trader_id") or "unknown")
    if kind.startswith("Position"):
        return f"{POSITION_EVENTS}.{component}"
    if kind.startswith("Order"):
        return f"{ORDER_EVENTS}.{component}"
    return f"{EVENTS}.system.{component}"


@dataclass
class EventEgress:
    """``XADD`` one Nautilus event per entry, in the engine's own envelope.

    The redis client is injected: the node process owns the connection, and the
    tests drive this with the same fake that backs the command stream.
    """

    client: Any  # redis.Redis
    trader_id: str

    def publish(self, payload: dict[str, Any]) -> str:
        """Append one event; returns its stream id.

        ``default=str`` matches ``RedisCommandBus.publish`` — a ``Decimal`` in
        a payload is serialised rather than raising, because losing a fill to a
        serialisation error would be the worst possible failure mode on this
        path.
        """
        topic = topic_for(payload)
        return str(
            self.client.xadd(
                stream_key(self.trader_id, topic),
                {
                    "topic": topic,
                    "type": "",
                    "payload": json.dumps(payload, default=str),
                    "encoding": JSON_ENCODING,
                },
            )
        )

    def heartbeat(
        self,
        *,
        node: str,
        nautilus_account_id: str,
        ts: float,
        reconciled: bool = True,
    ) -> str:
        """The beat that makes the node fit to take an order.

        ``reconciled`` is the engine's own reconciliation state, not a
        constant: a node that is still rebuilding its cache from the venue must
        report ``False`` so the gateway keeps refusing entries (ALG-3258's
        reconcile-before-entries rule, read from the event stream now).
        """
        from algobots.gateway.projection import iso

        return self.publish(
            {
                "type": "AlgoBotsHeartbeat",
                "node": node,
                "account_id": nautilus_account_id,
                "reconciled": reconciled,
                "ts": ts,
                "ts_event": iso(ts),
            }
        )


__all__ = [
    "ACCOUNT_EVENTS",
    "EVENTS",
    "HEARTBEAT_TOPIC",
    "JSON_ENCODING",
    "ORDER_EVENTS",
    "POSITION_EVENTS",
    "STREAMS_PREFIX",
    "EventEgress",
    "events_glob",
    "stream_key",
    "topic_for",
]
