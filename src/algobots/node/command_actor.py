"""The ``CommandActor``: one admitted command in, at most one venue call out.

P1.3's whole claim is one sentence — *sending the same command twice creates
one order* — and the design question is **where** that is true. The gateway
already dedupes in its own projection (``admission.admit`` returns the original
order on a replayed key). That is not enough on its own, and the reason is the
stream between them:

``algobots:cmd:<node>`` is a Redis stream read through a consumer group, which
is at-least-once by construction. A node that crashes between submitting an
order and ``XACK``-ing its entry will be handed that same entry again on
restart. No amount of care in the gateway prevents it, because the duplicate is
not a second request — it is the *same* request, delivered twice.

So dedupe here is answered by the execution surface, not by this object's
memory:

    the caller's idempotency key IS the Nautilus client order id,
    so "have I already submitted this?" is "does the venue know this id?"

:meth:`ExecutionSurface.status` asks exactly that, and in the real binding it
reads Nautilus' own cache — which is reconciled against the venue at startup.
That is why the guarantee survives a restart, and why this class keeps no
durable state of its own. An in-memory set would answer the question only for
the lifetime of the process that failed.

Two layers hold it, deliberately:

1. **This check**, which makes a duplicate a cheap logged no-op.
2. **Nautilus itself**, which denies a second order with an existing
   ``ClientOrderId``. Even if the two commands were handled concurrently and
   both passed step 1, the engine refuses the second — the venue is the
   backstop, not this code.

Cancellation is idempotent for the same reason, but on a different question.
A cancel is a no-op when the order is already terminal or already has a
cancellation in flight, which is a property of the *order*, not of the cancel
request's key: two cancels with two different keys for one order must still
cancel once.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from algobots.node.commands import CancelOrder, CommandRefused, SubmitOrder, parse

#: Nautilus ``OrderStatus`` names a node can no longer move an order out of.
#: A cancel against any of these is a no-op rather than an error: the caller
#: asked for an outcome that already holds.
TERMINAL = frozenset(
    {
        "FILLED",
        "CANCELED",
        "CANCELLED",  # tolerate either spelling, as node_events does
        "REJECTED",
        "EXPIRED",
        "DENIED",
    }
)

#: A cancellation already sent to the venue and not yet confirmed. Sending a
#: second one would be a duplicate request at the venue, not a faster cancel.
IN_FLIGHT_CANCEL = frozenset({"PENDING_CANCEL", "PENDING_UPDATE"})

# Outcomes. Every command produces exactly one of these, and the stream
# acknowledges the entry in all cases: none of them is improved by redelivery.
SUBMITTED = "submitted"
DUPLICATE = "duplicate"
CANCEL_SENT = "cancel_sent"
CANCEL_NOOP = "cancel_noop"
CANCEL_UNKNOWN = "cancel_unknown"
REFUSED = "refused"


class ExecutionSurface(Protocol):
    """The node's ``ExecutionClient``, narrowed to what a command needs.

    ADR 0001: everything that reaches a venue goes through here. The protocol
    is this small on purpose — a wider one would invite the actor to compute
    something (a price, a fill, a position) that only the engine may decide.
    """

    def status(self, client_order_id: str) -> str | None:
        """This id's Nautilus ``OrderStatus``, or ``None`` if unknown.

        Must be backed by the engine's reconciled cache rather than anything
        this process accumulated at runtime: it is the dedupe authority.
        """

    def submit(self, order: SubmitOrder) -> None:
        """Submit, using ``order.client_order_id`` as the client order id."""

    def cancel(self, client_order_id: str) -> None:
        """Request cancellation of a working order."""


@dataclass(frozen=True)
class Outcome:
    """What the actor did, for the log and for the stream's acknowledgement."""

    action: str
    client_order_id: str = ""
    code: str = ""
    reason: str = ""

    @property
    def executed(self) -> bool:
        """Did this reach the venue? The done-when counts these."""
        return self.action in (SUBMITTED, CANCEL_SENT)


@dataclass
class CommandActor:
    """Consumes admitted commands; submits or cancels through ``execution``.

    Deliberately not a Nautilus ``Actor`` subclass. The engine binding lives in
    :mod:`algobots.node.nautilus_actor`, which adapts a ``Strategy`` to
    :class:`ExecutionSurface`, so the rules above can be tested in CI without
    ``nautilus_trader`` installed — and they are, because a dedupe guarantee
    asserted only where the engine happens to be present is not a guarantee.
    """

    execution: ExecutionSurface
    node: str = ""
    #: Where refusals and duplicates go. Defaults to dropping them; the node
    #: wires this to its logger and P1.4 to its structured event log.
    log: Callable[[str, dict[str, Any]], None] | None = None

    def handle(self, body: Any) -> Outcome:
        """Act on one stream entry. Never raises for a bad command.

        The stream must keep moving: a command this node cannot execute is a
        refusal to record, not a poison entry to redeliver forever. Failures
        *inside* the venue call do propagate — those are worth a retry.
        """
        try:
            command = parse(body)
        except CommandRefused as refusal:
            return self._refuse(refusal, body)

        if isinstance(command, SubmitOrder):
            return self._submit(command)
        return self._cancel(command)

    # --- submit --------------------------------------------------------------

    def _submit(self, order: SubmitOrder) -> Outcome:
        existing = self.execution.status(order.client_order_id)
        if existing is not None:
            # The venue already knows this id. Whatever state it is in, this
            # command has been executed once — which is all it ever asked for.
            self._emit(
                "command.duplicate",
                {"client_order_id": order.client_order_id, "status": existing},
            )
            return Outcome(DUPLICATE, order.client_order_id, "duplicate", f"already {existing}")

        self.execution.submit(order)
        self._emit(
            "command.submitted",
            {
                "client_order_id": order.client_order_id,
                "account_id": order.account_id,
                "symbol": order.symbol,
                "side": order.side,
                "qty": str(order.qty),
            },
        )
        return Outcome(SUBMITTED, order.client_order_id)

    # --- cancel --------------------------------------------------------------

    def _cancel(self, request: CancelOrder) -> Outcome:
        status = self.execution.status(request.client_order_id)
        if status is None:
            # Nothing to cancel. Not an error the stream should retry: the
            # gateway only issues a cancel for an order it admitted, so an
            # unknown id here means this node never got the submission —
            # and a cancel cannot create the order it would cancel.
            self._emit("command.cancel_unknown", {"client_order_id": request.client_order_id})
            return Outcome(
                CANCEL_UNKNOWN,
                request.client_order_id,
                "unknown_order",
                "no such order on this node",
            )

        if status.upper() in TERMINAL or status.upper() in IN_FLIGHT_CANCEL:
            self._emit(
                "command.cancel_noop",
                {"client_order_id": request.client_order_id, "status": status},
            )
            return Outcome(
                CANCEL_NOOP, request.client_order_id, "already_cancelling", f"order is {status}"
            )

        self.execution.cancel(request.client_order_id)
        self._emit(
            "command.cancel_sent",
            {"client_order_id": request.client_order_id, "key": request.idempotency_key},
        )
        return Outcome(CANCEL_SENT, request.client_order_id)

    # --- plumbing ------------------------------------------------------------

    def _refuse(self, refusal: CommandRefused, body: Any) -> Outcome:
        client_order_id = ""
        if isinstance(body, dict):
            client_order_id = str(body.get("client_order_id") or "")
        self._emit(
            "command.refused",
            {"code": refusal.code, "reason": refusal.reason, "client_order_id": client_order_id},
        )
        return Outcome(REFUSED, client_order_id, refusal.code, refusal.reason)

    def _emit(self, event: str, fields: dict[str, Any]) -> None:
        if self.log is not None:
            self.log(event, {"node": self.node, **fields} if self.node else fields)


__all__ = [
    "CANCEL_NOOP",
    "CANCEL_SENT",
    "CANCEL_UNKNOWN",
    "DUPLICATE",
    "IN_FLIGHT_CANCEL",
    "REFUSED",
    "SUBMITTED",
    "TERMINAL",
    "CommandActor",
    "ExecutionSurface",
    "Outcome",
]
