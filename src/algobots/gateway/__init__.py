"""The AlgoBots gateway — ROADMAP-v3 Phase 1 (P1.1, ALG-3369).

The chokepoint between NoFX and the NautilusTrader nodes. NoFX never talks to
a node, a broker or Redis; it talks here. Every route this package serves is
declared in ``contracts/gateway.openapi.yaml`` first (roadmap rule 2) — adding
one here without adding it there is a failing test, not a judgement call.

The surface is the bridge v0.1 control plane (``algobots.bridge``,
docs/bridge.md, ALG-3340) promoted to the gateway, per the CEO's Oct 14 review:

- the gateway **admits** intents and never executes them,
- a Nautilus ``ExecutionClient`` in the node is the only thing that fills
  (ADR 0001), and
- the node's event stream is the only source of orders, fills, positions and
  balances — this process holds no parallel simulator.

The module boundaries are the Phase 1 sprint boundaries:

``admission``   the refusal order, lifted from the bridge unchanged.
``projection``  what the node has told us, queryable. P1.2 replaces the
                in-memory implementation with the Postgres projection; the
                protocol is what it has to satisfy.
``node_events`` Nautilus event JSON (as captured in P0.3) folded into that
                projection. The only place the node's wire shape is known.
``nodes``       which node serves which account, whether it is fit to take an
                order, and the ``algobots:cmd:<node>`` command stream P1.3's
                ``CommandActor`` reads.
``fixture_node`` a fake node that speaks that same wire shape, so the contract
                tests run with no Nautilus, no broker and no Redis.
"""

from algobots.gateway.app import build_gateway
from algobots.gateway.errors import GatewayError

__all__ = ["GatewayError", "build_gateway"]
