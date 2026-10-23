"""The gateway's half of the event path: Redis streams folded into Postgres.

:mod:`algobots.node.event_egress` publishes; this consumes. Together they are
the leg P1.2 and P1.3 left open — the reason a fill could reach the gateway's
projection at all is this loop, and GATE G1's two-second budget is mostly spent
here.

Three decisions worth the words:

**Keys are discovered, not configured.** Nautilus' topics carry the emitting
component (``events.order.{strategy_id}``, ``events.account.{account_id}``), so
the full set of streams is not known until a node has emitted on them. A
configured list would silently miss the stream a newly started strategy writes
to, and missing a stream here means missing fills. So each pass re-scans
``trader-*:algobots:events.*`` and reads every key it finds.

**A new stream is read from the beginning**, not from its tail. The alternative
loses every event published between the stream's creation and the scan that
noticed it. Re-reading is safe because the fold is idempotent — P1.2 dedupes
fills on ``(client_order_id, trade_id)`` and ``node_events`` drops events for
orders this gateway never admitted — and "safe to replay" is a property this
path has to have anyway: Nautilus' streams outlive the gateway process, so a
restart re-reads whatever the cursor had not reached.

**``XREAD``, not a consumer group.** The streams belong to the engine, which
creates no group, and the gateway is the only reader. A group would add a
pending list whose recovery semantics are already provided by the durable
projection: an event that was read but not folded is re-read after a restart
because the cursor only advances once ``ingest`` has returned.

What this loop deliberately does *not* do is interpret. Every payload goes to
:func:`algobots.gateway.node_events.ingest` via ``node_events.normalize`` (the
wire-shape module owns both engine generations' envelopes), and an event that
module does not recognise is dropped rather than guessed at.

**Only the per-component topics are folded.** Nautilus 2.0.0rc6 publishes each
order event twice: on ``events.order.<strategy>`` — every event for the
strategy, in order — and again on a per-type topic such as
``events.order_filled.<instrument>``. Each stream is read independently, so
folding both would replay ``OrderSubmitted`` after ``OrderFilled`` and walk a
filled order back to ``submitted``. :data:`FOLDED_TOPICS` keeps the ordered
stream and drops the copies (ALG-3405).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from algobots.gateway import node_events as NE
from algobots.gateway.nodes import NodeRegistry
from algobots.gateway.projection import Projection
from algobots.node.event_egress import JSON_ENCODING, events_glob

#: How long ``XREAD`` waits for a new entry, in ms. Short, because the scan for
#: new stream keys only happens between reads: this is the upper bound on how
#: late the gateway notices a *stream* that did not exist, and it is paid once
#: per node rather than once per event.
BLOCK_MS = 50

#: Entries per stream per read.
BATCH = 500

#: Where a stream the gateway has not seen before is read from. ``"0"`` is the
#: beginning — see the module docstring on why the tail would lose events.
FROM_START = "0"


#: ``events.<kind>.<component>`` topics whose events are folded. ``order``,
#: ``position`` and ``account`` are the 1.231 capture's and rc6's ordered
#: streams; ``heartbeat`` is :mod:`algobots.node.event_egress`'s.
FOLDED_TOPICS = frozenset({"order", "position", "account", "heartbeat"})


def _text(value: Any) -> Any:
    return value.decode() if isinstance(value, bytes | bytearray) else value


def decode(fields: dict[Any, Any]) -> dict[str, Any] | None:
    """One stream entry -> the Nautilus event it carries, or ``None``.

    ``None`` for anything this gateway must not treat as state: a non-JSON
    encoding (the engine can be configured for msgpack, and decoding it as text
    would produce garbage that looked like an event), a payload that is not
    valid JSON, or a payload that is not an object.
    """
    body = {str(_text(k)): _text(v) for k, v in (fields or {}).items()}
    encoding = str(body.get("encoding") or JSON_ENCODING)
    if encoding.lower() != JSON_ENCODING.lower():
        return None
    parts = str(body.get("topic") or "").split(".")
    if len(parts) > 1 and parts[1] not in FOLDED_TOPICS:
        return None
    raw = body.get("payload")
    if raw is None:
        return None
    if isinstance(raw, dict):
        parsed: Any = raw
    else:
        try:
            parsed = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            return None
    if not isinstance(parsed, dict):
        return None
    return NE.normalize(parsed, str(body.get("type") or ""))


@dataclass
class NodeEventIngest:
    """Reads every node's event streams and folds them into the projection.

    One instance per gateway process. ``registry`` is the same object the HTTP
    routes hold, which is what makes a heartbeat read off the stream change the
    answer ``/health`` and ``POST /orders`` give — the node's liveness has one
    source, not a file and a stream that can disagree.
    """

    client: Any  # redis.Redis
    registry: NodeRegistry
    projection: Projection
    trader_id: str = "*"
    block_ms: int = BLOCK_MS
    batch: int = BATCH
    log: Callable[[str, dict[str, Any]], None] | None = None
    #: Stream key -> last entry id folded. The in-process half of the cursor;
    #: the durable half is the projection itself, which is why losing this map
    #: costs a re-read and not a wrong answer.
    cursors: dict[str, str] = field(default_factory=dict)
    #: Events folded into the projection (i.e. ones the contract exposes).
    #: Bounded like ``CommandStream.recent``: the durable record is the
    #: projection's event table, not this.
    folded: int = 0

    @property
    def glob(self) -> str:
        return events_glob(self.trader_id)

    def discover(self) -> list[str]:
        """Stream keys this gateway has not read yet, now registered at ``0``."""
        found = [str(_text(key)) for key in self.client.scan_iter(match=self.glob)]
        fresh = [key for key in found if key not in self.cursors]
        for key in fresh:
            self.cursors[key] = FROM_START
        return fresh

    def _read(self) -> Iterable[tuple[Any, Any]]:
        if not self.cursors:
            return []
        return self.client.xread(dict(self.cursors), count=self.batch, block=self.block_ms) or []

    def poll(self) -> list[dict[str, Any]]:
        """One pass: scan for new streams, read them, fold what they carry.

        Returns the contract ``Event``s appended to the projection — the
        entries that produced nothing (a system event, a replayed fill, an
        order this gateway never admitted) are counted in neither the result
        nor :attr:`folded`.
        """
        self.discover()
        appended: list[dict[str, Any]] = []
        for raw_key, entries in self._read():
            key = str(_text(raw_key))
            for entry_id, fields in entries:
                payload = decode(fields)
                if payload is not None:
                    event = NE.ingest(payload, registry=self.registry, projection=self.projection)
                    if event is not None:
                        appended.append(event)
                        self.folded += 1
                # The cursor advances only after the fold, so a crash mid-fold
                # re-reads the entry rather than skipping it. Advancing it for
                # an undecodable entry too is deliberate: re-reading one would
                # block the stream behind it forever.
                self.cursors[key] = str(_text(entry_id))
        return appended

    def run(self, *, until: Callable[[], bool] | None = None) -> None:
        """Poll until told to stop. The gateway process' event loop.

        Errors propagate for the same reason ``CommandStream.run`` lets them:
        a loop that swallowed a lost Redis connection would leave the gateway
        serving a projection that had quietly stopped advancing, which reads to
        NoFX as a market that stopped trading.
        """
        while until is None or not until():
            try:
                self.poll()
                if not self.cursors:
                    # No stream exists yet, so ``XREAD`` had nothing to block
                    # on and returned at once. A gateway that starts before any
                    # node has published is the normal case, and without this
                    # it would spin on ``SCAN`` until one does.
                    time.sleep(self.block_ms / 1000.0)
            except Exception as exc:
                self._log("event_ingest.error", {"error": str(exc)})
                raise

    def _log(self, event: str, fields: dict[str, Any]) -> None:
        if self.log is not None:
            self.log(event, fields)


__all__ = ["BATCH", "BLOCK_MS", "FOLDED_TOPICS", "FROM_START", "NodeEventIngest", "decode"]
