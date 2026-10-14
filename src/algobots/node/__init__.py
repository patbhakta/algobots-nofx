"""The node half of the gateway seam — what runs inside a Nautilus process.

``algobots.gateway`` admits intents and writes them to ``algobots:cmd:<node>``.
Nothing in that package executes. This package is the other side: it reads that
stream and submits through the node's own ``ExecutionClient``, which ADR 0001
makes the only thing allowed to put an order at a venue.

The split is deliberate. Modules here may import ``nautilus_trader``; modules
in ``algobots.gateway`` may not, because the gateway runs in the API process
where Nautilus is not installed. The one module here that does import it
(:mod:`algobots.node.nautilus_actor`) does so lazily, so the command logic
stays testable — and tested in CI — without the engine present.
"""

from __future__ import annotations

__all__: list[str] = []
