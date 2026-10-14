"""``algobots:cmd:<node>``, read as a consumer group.

The gateway's writer is ``RedisCommandBus.publish`` — one ``XADD`` per command
with the JSON in a single ``command`` field. This is the reader.

A consumer group, not a plain ``XREAD``, for one reason: **a restart may not
lose a command**. With a group, an entry handed to this consumer stays in its
pending list until ``XACK``, so a node that dies mid-submission is given the
entry again when it comes back. ``_drain_pending`` is that recovery path, and
it runs before any new entry is read — a command queued before the crash is
older than one queued after it, and acting on them out of order would reorder
a member's intent.

The cost of that choice is the duplicate, and it is the *right* cost to pay:
at-least-once delivery means this module will occasionally hand the actor a
command it has already executed. The actor is built for exactly that (see
:mod:`algobots.node.command_actor`), which is why the acknowledgement here is
unconditional on the *kind* of outcome — a duplicate is a successful outcome,
not a failure to retry.

What does block the acknowledgement is an exception out of ``handle``: an
unloaded instrument, a venue that refused the call. Those leave the entry
pending so it is retried, and the actor's dedupe is what makes that retry safe.

``redis`` is imported lazily and never at module scope: the API process does
not have the dependency (``nodes.RedisCommandBus`` makes the same note), and
this module must stay importable for the tests that drive it with a fake.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any

from algobots.node.command_actor import CommandActor, Outcome

#: The consumer group every node uses on its own stream. One group per stream,
#: because one node owns one stream: the group exists for the pending-list
#: semantics, not to fan work out to competing consumers.
GROUP = "algobots-node"

#: How long ``XREADGROUP`` waits for a new entry before returning empty, in ms.
#: Long enough that an idle node is not a busy loop, short enough that a
#: shutdown signal is noticed promptly.
BLOCK_MS = 5_000

#: Entries per read. Commands are rare and latency matters more than batching.
BATCH = 10


def stream_key(node: str) -> str:
    """The stream the gateway writes this node's commands to."""
    return f"algobots:cmd:{node}"


def decode(fields: dict[Any, Any]) -> Any:
    """One stream entry's fields -> the command JSON the gateway wrote.

    Tolerates ``bytes`` keys and values so the caller may construct its client
    with or without ``decode_responses=True``.
    """

    def text(value: Any) -> Any:
        return value.decode() if isinstance(value, bytes | bytearray) else value

    body = {text(k): text(v) for k, v in (fields or {}).items()}
    raw = body.get("command")
    if raw is None:
        return None
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Not parseable as JSON: hand it to the actor as-is so it produces
            # a refusal (and so the entry is acknowledged) rather than
            # crashing the loop on a malformed write.
            return raw
    return raw


@dataclass
class CommandStream:
    """Reads one node's command stream and feeds :class:`CommandActor`.

    The redis client is injected rather than constructed so the done-when test
    can drive the whole loop — pending list included — without a server.
    """

    client: Any  # redis.Redis
    actor: CommandActor
    node: str
    group: str = GROUP
    consumer: str = "node-1"
    block_ms: int = BLOCK_MS
    batch: int = BATCH
    log: Callable[[str, dict[str, Any]], None] | None = None
    #: Outcomes, newest last. Bounded so a long-running node does not grow it
    #: without limit; the durable record is the node's event stream, not this.
    recent: list[Outcome] = field(default_factory=list)
    _recent_max: int = 256

    @property
    def key(self) -> str:
        return stream_key(self.node)

    def ensure_group(self) -> None:
        """Create the group if it is not there. Safe to call repeatedly.

        ``mkstream`` matters: the node usually starts before the gateway has
        ever written a command, and without it the group creation would fail
        on a stream that does not exist yet.
        """
        try:
            self.client.xgroup_create(self.key, self.group, id="0", mkstream=True)
        except Exception as exc:  # redis.exceptions.ResponseError — not imported here
            if "BUSYGROUP" not in str(exc):
                raise

    def _read(self, cursor: str) -> list[Any]:
        """``XREADGROUP`` at ``cursor``: ``"0"`` for pending, ``">"`` for new."""
        return (
            self.client.xreadgroup(
                self.group,
                self.consumer,
                {self.key: cursor},
                count=self.batch,
                # Re-reading the pending list must never block: an empty
                # pending list is the normal case and the answer is immediate.
                block=self.block_ms if cursor == ">" else None,
            )
            or []
        )

    def _entries(self, response: list[Any]) -> Iterator[tuple[Any, dict[Any, Any]]]:
        for _stream, entries in response:
            yield from entries

    def _handle(self, entry_id: Any, fields: dict[Any, Any]) -> Outcome:
        """One entry: act, then acknowledge.

        The order is not negotiable, and it is the pessimistic one. Acting
        before acknowledging risks a duplicate (the actor absorbs it);
        acknowledging before acting risks a *lost* command, which nothing
        downstream can recover.
        """
        outcome = self.actor.handle(decode(fields))
        self.client.xack(self.key, self.group, entry_id)
        self._remember(outcome)
        return outcome

    def _remember(self, outcome: Outcome) -> None:
        self.recent.append(outcome)
        if len(self.recent) > self._recent_max:
            del self.recent[: -self._recent_max]

    def drain_pending(self) -> list[Outcome]:
        """Re-handle everything delivered to this consumer but never acked.

        The restart path. Runs to exhaustion before new entries are read.
        """
        done: list[Outcome] = []
        while True:
            batch = list(self._entries(self._read("0")))
            if not batch:
                return done
            for entry_id, fields in batch:
                done.append(self._handle(entry_id, fields))

    def poll(self) -> list[Outcome]:
        """One pass over whatever is new. Returns the outcomes it produced."""
        return [
            self._handle(entry_id, fields) for entry_id, fields in self._entries(self._read(">"))
        ]

    def run(self, *, until: Callable[[], bool] | None = None) -> None:
        """The node's command loop: recover, then poll until told to stop.

        ``until`` is the shutdown predicate the node's supervisor supplies;
        without one this blocks forever, which is what a long-running node
        wants and what a test never passes.
        """
        self.ensure_group()
        self.drain_pending()
        while until is None or not until():
            try:
                self.poll()
            except Exception as exc:
                # Logged and propagated, not swallowed. A failure here is a
                # broken node (lost connection, an unexecutable command the
                # venue keeps rejecting), and a loop that caught it would look
                # healthy while doing nothing. The supervisor owns the restart
                # policy; the unacked entry is still pending when the node
                # comes back, and the actor's dedupe makes replaying it safe.
                self._log("command_stream.error", {"error": str(exc)})
                raise

    def _log(self, event: str, fields: dict[str, Any]) -> None:
        if self.log is not None:
            self.log(event, {"node": self.node, **fields})


__all__ = ["BATCH", "BLOCK_MS", "GROUP", "CommandStream", "decode", "stream_key"]
