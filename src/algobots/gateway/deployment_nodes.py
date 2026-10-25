"""Frozen Studio deployments as gateway nodes (ALG-3431).

The deployment supervisor spawns one paper node per RUNNING deployment
(:func:`algobots.api.deployments.runtime.launch_spec`). The gateway learns the
same ``(node, venue)`` pair from Postgres rather than ``ALGOBOTS_GATEWAY_NODES``,
so a funder's deploy needs no ``.env`` edit, and its fills fold onto the
deployment's own account. ``gateway_orders.node`` is the attribution:
``deployment-<hex>`` names exactly one deployment.

Lifecycle is rechecked here, not only in the supervisor. A deployment that is
paused, stopped or breaker-halted keeps its node registered with
:attr:`~algobots.gateway.nodes.Node.halted` set: new orders are refused with
``worker_unavailable`` while fills already in flight still fold. The kill
switch therefore does not depend on the supervisor noticing first.

The dispatcher authenticates with one bearer token that is granted exactly the
deployment accounts currently registered, never the static demo accounts.
"""

from __future__ import annotations

import hmac
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from algobots.api.deployments.runtime import deployment_rows_statement, node_identity
from algobots.api.deployments.service import effective_state
from algobots.gateway.auth import Caller, Sessions
from algobots.gateway.nodes import Node, NodeRegistry

log = logging.getLogger("algobots.gateway")

DISPATCHER = "deployment-dispatcher"

#: Seconds between Postgres reads of the deployment table.
SYNC_S = 2.0


def deployment_node(deployment: Any) -> Node:
    node, venue = node_identity(deployment.id)
    return Node(
        node=node,
        account_id=str(deployment.account_id),
        display_name=f"Deployment {deployment.id}",
        venue=venue,
        nautilus_account_id=f"{venue}-001",
    )


def halt_reason(deployment: Any, account: Any, fleet: Any) -> str:
    state, _ = effective_state(deployment, fleet)
    if state != "running":
        return f"deployment {deployment.id} is {state}"
    if account.mode != "paper" or account.status != "active":
        return f"deployment {deployment.id}: account is not an active paper account"
    return ""


def sync(registry: NodeRegistry, rows: list[tuple[Any, Any, Any]]) -> list[str]:
    """Register running deployments, halt the rest. Returns newly added nodes.

    A stopped deployment that was never registered (e.g. after a gateway
    restart) stays out of the registry; one already registered is only halted.
    One account, one node: a second deployment on an account already served by
    another node is refused rather than sharing its fills.
    """
    added = []
    for deployment, account, fleet in rows:
        reason = halt_reason(deployment, account, fleet)
        spec = deployment_node(deployment)
        existing = registry.nodes.get(spec.node)
        if existing is not None:
            existing.halted = reason
            continue
        if reason:
            continue
        owner = registry.by_account(spec.account_id)
        if owner is not None:
            log.warning("gateway: %s not registered, account served by %s", spec.node, owner.node)
            continue
        registry.add(spec)
        added.append(spec.node)
    return added


@dataclass(frozen=True)
class DispatchSessions:
    """Static sessions plus one dispatcher token scoped to deployment nodes."""

    base: Sessions
    token: str
    registry: NodeRegistry

    def caller(self, token: str | None) -> Caller | None:
        if token and self.token and hmac.compare_digest(token, self.token):
            accounts = tuple(
                n.account_id for n in self.registry.accounts() if n.node.startswith("deployment-")
            )
            return Caller(DISPATCHER, accounts)
        return self.base.caller(token)


def read_rows(engine: Any) -> list[tuple[Any, Any, Any]]:
    from sqlalchemy.orm import Session

    with Session(engine) as session:
        return [tuple(row) for row in session.execute(deployment_rows_statement()).all()]


def sync_forever(
    registry: NodeRegistry,
    read: Callable[[], list],
    on_added: Callable[[list[str]], None],
    stopped: threading.Event | None = None,
) -> None:
    """Keep the registry in step with Postgres; a failed read halts every node.

    Failing closed matters: if the gateway cannot see that a deployment was
    stopped, it must not keep admitting that deployment's orders.
    """
    stopped = stopped or threading.Event()
    while not stopped.is_set():
        try:
            added = sync(registry, read())
            if added:
                on_added(added)
                log.info("gateway: registered deployment node(s) %s", added)
        except Exception:
            log.exception("gateway: deployment sync failed; halting deployment nodes")
            for node in registry.accounts():
                if node.node.startswith("deployment-"):
                    node.halted = "deployment lifecycle unreadable"
        stopped.wait(SYNC_S)


__all__ = [
    "DISPATCHER",
    "DispatchSessions",
    "deployment_node",
    "halt_reason",
    "read_rows",
    "sync",
    "sync_forever",
]
